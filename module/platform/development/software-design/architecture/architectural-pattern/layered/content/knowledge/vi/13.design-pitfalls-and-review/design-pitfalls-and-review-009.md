# Đánh giá thiết kế bằng kịch bản thay đổi và đồ thị phụ thuộc thực tế

Một sơ đồ kiến trúc đẹp chưa đủ chứng minh hệ thống được phân tầng tốt. Thiết kế chỉ bộc lộ chất lượng khi có yêu cầu thay đổi: đổi hợp đồng API, thêm một kênh giao tiếp, thay quy tắc nghiệp vụ hoặc chuyển hệ quản trị cơ sở dữ liệu. Một thiết kế tốt giúp thay đổi tập trung ở những thành phần sở hữu trách nhiệm đó; một thiết kế yếu khiến thay đổi lan qua nhiều tầng không liên quan.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — có thể đánh giá thiết kế bằng cách kết hợp **kịch bản thay đổi cụ thể** với **đồ thị phụ thuộc lấy từ mã nguồn và cấu hình thực tế**. Kịch bản cho biết hệ thống cần thay đổi điều gì; đồ thị cho thấy những thành phần nào đang phụ thuộc vào nhau và thay đổi có thể lan tới đâu. Cách đánh giá này giúp phát hiện phụ thuộc ngược chiều, chu trình, tầng bị bỏ qua, lớp trung tâm quá tải và khoảng cách giữa kiến trúc dự định với kiến trúc đang tồn tại.

## 1. Vì sao cần xem cả kịch bản thay đổi lẫn đồ thị phụ thuộc?

Một thiết kế có thể có các package tên là presentation, application, domain và infrastructure nhưng vẫn không giữ được ranh giới. Ví dụ, domain có thể import một JPA entity; controller có thể truy vấn repository trực tiếp; một service nghiệp vụ có thể gọi thẳng HTTP client. Tên package thể hiện ý định, còn import, lời gọi, cấu hình và liên kết dữ liệu mới cho thấy hệ thống thực sự được kết nối ra sao.

Ngược lại, một đồ thị phụ thuộc có vẻ gọn cũng chưa chắc đáp ứng tốt nhu cầu thay đổi. Nếu một lớp duy nhất có trách nhiệm xử lý nhiều chính sách không liên quan, đồ thị có thể không có chu trình nhưng thay đổi một chính sách vẫn buộc sửa nhiều nhánh trong cùng lớp. Vì vậy, cần đặt câu hỏi thiết kế trong bối cảnh yêu cầu thay đổi thực tế.

| Công cụ đánh giá | Trả lời câu hỏi | Bằng chứng cần xem |
|---|---|---|
| Kịch bản thay đổi | Khi yêu cầu X xuất hiện, thành phần nào cần thay đổi và thành phần nào nên ổn định? | Yêu cầu nghiệp vụ, hợp đồng API, quy tắc, quyết định thiết kế và lịch sử thay đổi nếu có. |
| Đồ thị phụ thuộc | Thành phần nào đang tham chiếu, gọi hoặc cần thành phần nào? | Import/type reference, module dependency, lời gọi, cấu hình DI, schema và giao tiếp runtime. |
| Kiểm thử kiến trúc | Quy tắc phụ thuộc có được thực thi tự động không? | ArchUnit, kiểm tra module/build, rule trong CI. |
| Kiểm thử theo kịch bản | Hành vi có thay đổi đúng phạm vi khi áp dụng yêu cầu không? | Unit, integration, contract test và kết quả build. |

Kịch bản giúp đánh giá khả năng thích nghi; đồ thị giúp giải thích nguyên nhân cấu trúc. Kết hợp hai góc nhìn tránh kết luận chỉ dựa trên số package, số lớp hoặc một sơ đồ do nhóm tự vẽ.

## 2. Xây dựng kịch bản thay đổi có thể kiểm chứng

Một kịch bản tốt mô tả một thay đổi đủ cụ thể để lần theo mã nguồn. Tránh các câu quá rộng như “hệ thống cần dễ mở rộng” hoặc “database có thể thay đổi”. Hãy nêu rõ tác nhân, thay đổi, quy tắc giữ nguyên và kết quả mong đợi.

Ví dụ:

- API đặt hàng đổi tên trường JSON items thành lines nhưng ý nghĩa đặt hàng không đổi.
- Doanh nghiệp thay chính sách giảm giá cho khách hàng thành viên.
- Hệ thống bổ sung CLI để nhân viên tạo đơn qua cùng ca sử dụng.
- PostgreSQL được thay bằng một hệ quản trị khác nhưng quy tắc tạo đơn không đổi.
- Một message consumer nhận yêu cầu đặt hàng từ hệ thống đối tác.
- Ca sử dụng cần ghi thêm audit record khi trạng thái đơn thay đổi.

Với mỗi kịch bản, ghi lại bốn nội dung:

1. **Điểm thay đổi:** yêu cầu hoặc quyết định nào thay đổi?
2. **Thành phần dự kiến thay đổi:** nơi sở hữu hợp đồng, quy tắc hoặc chi tiết kỹ thuật đó.
3. **Thành phần cần giữ ổn định:** các tầng hoặc kênh không có lý do nghiệp vụ để thay đổi.
4. **Bằng chứng chấp nhận:** test, hợp đồng hoặc quan sát nào chứng minh thay đổi đã được giới hạn đúng?

Bảng dưới đây là ví dụ cho một ứng dụng đặt hàng phân tầng:

| Kịch bản | Thành phần dự kiến thay đổi | Thành phần nên giữ ổn định |
|---|---|---|
| Đổi tên trường JSON của API | Request DTO, mapper hoặc controller, API contract test | Domain Order và chính sách giá |
| Thay chính sách giảm giá | Domain policy/value object và test nghiệp vụ | REST controller, JPA mapping |
| Thêm CLI tạo đơn | CLI adapter và test adapter | PlaceOrderUseCase, domain và repository contract nếu mục tiêu nghiệp vụ không đổi |
| Đổi database engine | Persistence adapter, mapping, migration và integration test | Domain model và hợp đồng ca sử dụng |
| Thêm message consumer | Message adapter, schema/message contract và test consumer | Quy tắc đặt hàng dùng chung |
| Ghi audit trong ca sử dụng | Hợp đồng/cổng audit và phần điều phối liên quan | Hợp đồng HTTP nếu response không đổi |

Đây là dự đoán ban đầu, không phải luật cứng. Một thay đổi chính sách có thể kéo theo thay đổi schema nếu cần lưu thêm dữ liệu; đổi database có thể buộc điều chỉnh một kiểu dữ liệu nếu domain đã phụ thuộc vào kiểu riêng của vendor. Điều quan trọng là giải thích được mỗi thay đổi lan sang đâu và vì sao.

## 3. Đọc đồ thị phụ thuộc thực tế

Đồ thị phụ thuộc biểu diễn thành phần dưới dạng nút (node) và quan hệ phụ thuộc dưới dạng cạnh (edge). Nút có thể là class, package, module hoặc deployment unit. Cạnh có thể biểu diễn một lớp import kiểu khác, module khai báo dependency tới module khác, một thành phần gọi API của thành phần khác hoặc một runtime service gửi request tới service khác.

Cần xác định rõ loại cạnh đang xem. Có ít nhất ba góc nhìn khác nhau:

- **Phụ thuộc mã nguồn/biên dịch:** một class dùng kiểu, interface hoặc annotation của class khác; một module khai báo dependency tới module khác.
- **Luồng gọi khi chạy:** một request đi từ controller qua use case tới repository adapter và database. Dependency injection có thể khiến lớp triển khai được chọn lúc chạy.
- **Phụ thuộc vận hành/tích hợp:** ứng dụng cần database, message broker, biến môi trường, schema message, dịch vụ ngoài hoặc quyền truy cập mạng.

Không nên trộn các loại cạnh này thành một sơ đồ mà không chú thích. Ví dụ, luồng gọi lúc chạy có thể là application gọi một interface repository rồi runtime dispatch tới JPA adapter. Nhưng hướng phụ thuộc mã nguồn có thể là adapter import interface do application định nghĩa. Hai sơ đồ trả lời hai câu hỏi khác nhau.

### Đồ thị phụ thuộc mã nguồn của một ứng dụng phân tầng

Giả sử ứng dụng có các package:

~~~text
com.example.shop
├── presentation
├── application
├── domain
└── infrastructure
    └── persistence
~~~

Một cấu trúc phụ thuộc có thể được tổ chức như sau:

~~~mermaid
flowchart BT
    Domain["Domain<br/>Order, Money, policy"]
    Application["Application<br/>Use cases, ports"]
    Presentation["Presentation<br/>REST, CLI adapters"]
    Infrastructure["Infrastructure<br/>JPA, HTTP, broker adapters"]

    Application --> Domain
    Presentation --> Application
    Infrastructure --> Application
    Infrastructure --> Domain
~~~

Sơ đồ này mô tả **phụ thuộc mã nguồn** theo hướng từ bên sử dụng kiểu/hợp đồng tới bên được tham chiếu. Application có thể định nghĩa interface OrderRepository; infrastructure triển khai interface đó. Domain không cần import Spring Web hoặc JPA. Tùy cách tổ chức, một số cổng có thể được đặt trong package domain hoặc application; điều quan trọng là hợp đồng được sở hữu bởi phần bên trong cần nó, còn adapter kỹ thuật phụ thuộc vào hợp đồng đó.

Khi chạy, luồng xử lý có thể khác hướng nhìn:

~~~mermaid
flowchart LR
    Request["HTTP request"] --> Controller["OrderController"]
    Controller --> UseCase["PlaceOrderUseCase"]
    UseCase --> Service["PlaceOrderService"]
    Service --> Domain["Order.place(...)"]
    Service --> Port["OrderRepository"]
    Port -.runtime implementation.-> Adapter["JpaOrderRepositoryAdapter"]
    Adapter --> Database[("PostgreSQL")]
~~~

Controller gọi use case; service gọi repository interface; Spring inject adapter JPA để thực hiện thao tác lưu trữ. Cạnh nét đứt thể hiện việc triển khai hợp đồng lúc chạy, không có nghĩa application cần import lớp JpaOrderRepositoryAdapter.

## 4. Tìm đồ thị từ mã nguồn thay vì chỉ tin sơ đồ

Đồ thị trong tài liệu kiến trúc thường thể hiện ý định. Để đánh giá thực tế, cần đối chiếu với mã nguồn, build configuration và wiring.

Một số nguồn bằng chứng:

- **Import và type reference:** tìm các import giữa package, field/constructor type, annotation và kiểu trả về.
- **Build dependency:** xem dependency giữa Gradle/Maven module; module nào kéo framework hoặc adapter vào module nào.
- **Static bytecode dependency:** công cụ như jdeps có thể cho thấy package/module nào tham chiếu class nào trong bytecode đã biên dịch.
- **Dependency injection:** xem cấu hình Spring, ComponentScan, Bean, profile và qualifier để biết implementation nào được nối vào port.
- **Runtime call và network:** dùng trace, log hoặc quan sát request để biết service nào thực sự gọi service nào.
- **Storage/schema:** xem repository, migration, SQL, ORM mapping và database view/trigger nếu chúng tạo ra phụ thuộc dữ liệu.
- **Message/API contract:** xem schema sự kiện, topic, endpoint, phiên bản API và các consumer phụ thuộc vào cấu trúc đó.

Ví dụ, dependency tree của Gradle có thể cho biết module application đang phụ thuộc module infrastructure. Đó là bằng chứng cần kiểm tra nếu mục tiêu là để application chỉ phụ thuộc hợp đồng bên trong. Một đồ thị package có thể cho thấy domain import org.springframework.web; một trace runtime có thể cho thấy controller đang gọi thẳng một dịch vụ ngoài thay vì đi qua ca sử dụng.

Không một công cụ đơn lẻ nào nhìn thấy toàn bộ hệ thống. jdeps chủ yếu phân tích tham chiếu tĩnh trong bytecode, không phát hiện đầy đủ phụ thuộc được tạo qua reflection, tên bean trong cấu hình, truy vấn SQL động, biến môi trường hoặc giao tiếp mạng. Cần kết hợp nhiều nguồn và xác nhận bằng test hoặc quan sát runtime.

## 5. Đánh giá một kịch bản bằng cách lần theo đồ thị

Hãy xét kịch bản: thay PostgreSQL bằng một hệ quản trị cơ sở dữ liệu khác, trong khi nghiệp vụ đặt hàng không đổi.

Quy trình đánh giá:

1. Xác định điểm thay đổi là công nghệ lưu trữ và schema, không phải ý nghĩa của Order.
2. Tìm mọi cạnh từ domain/application tới kiểu đặc thù PostgreSQL, Hibernate hoặc Spring Data.
3. Tìm adapter, mapping, truy vấn native SQL, migration và cấu hình datasource liên quan.
4. Xác định phần nào phải thay đổi để adapter mới triển khai cùng hợp đồng repository.
5. Chạy domain/application test để chứng minh quy tắc không đổi; chạy repository integration test trên engine mới để chứng minh adapter hoạt động.
6. Ghi nhận mọi phụ thuộc ngoài dự kiến, chẳng hạn domain dùng PGobject, SQL PostgreSQL hoặc kiểu dữ liệu JSONB trực tiếp.

Nếu thay database buộc phải sửa Order, Money và PlaceOrderService chỉ vì các lớp này import kiểu của vendor, đó là dấu hiệu chi tiết lưu trữ đã rò vào bên trong. Nếu chỉ adapter, mapping và migration cần đổi, ranh giới lưu trữ đang hoạt động như mong đợi.

Một kịch bản khác: thêm CLI để tạo đơn. Hãy tìm xem quy tắc đặt hàng hiện nằm ở đâu. Nếu controller đang chứa việc tải sản phẩm, tính giá và xác nhận đơn, CLI sẽ phải sao chép logic đó hoặc gọi controller nội bộ. Đây là dấu hiệu ca sử dụng chưa được đặt ở tầng ứng dụng. Nếu controller và CLI đều có thể chuyển dữ liệu thành PlaceOrderCommand rồi gọi cùng PlaceOrderUseCase, phần nghiệp vụ có thể được tái sử dụng.

## 6. Các tín hiệu cảnh báo trong đồ thị phụ thuộc

Một số cấu trúc thường đáng được xem xét:

| Tín hiệu | Điều có thể xảy ra | Câu hỏi đánh giá |
|---|---|---|
| Chu trình giữa package/module | Hai nhóm trách nhiệm cần biết lẫn nhau, khó build/test độc lập. | Có thể đưa hợp đồng chung về module sở hữu nó hoặc tách trách nhiệm không? |
| Domain phụ thuộc presentation/infrastructure | Quy tắc nghiệp vụ bị gắn với giao thức hoặc công nghệ. | Có thể chuyển phụ thuộc sang interface/kiểu thuần của domain không? |
| Application import implementation JPA/HTTP cụ thể | Ca sử dụng khó thay adapter và khó test độc lập. | Application có thể phụ thuộc port và adapter triển khai port không? |
| Presentation gọi repository trực tiếp | Bỏ qua điều phối, quyền, transaction hoặc quy tắc dùng chung. | Đây có thực sự là truy vấn đọc đơn giản được cho phép, hay cần một use case? |
| Một lớp có quá nhiều fan-in/fan-out | Lớp có thể đang là điểm phụ thuộc trung tâm hoặc ôm nhiều trách nhiệm. | Các phụ thuộc có thuộc cùng một lý do thay đổi không? |
| Nhiều adapter phụ thuộc trực tiếp vào một lớp cụ thể ở tầng trong | Khó thay đổi hợp đồng và có thể làm lộ chi tiết triển khai. | Cần interface/port ổn định hơn hay không? |
| Phụ thuộc runtime không có timeout/retry rõ ràng | Một tier lỗi có thể kéo theo các tier khác. | Hành vi khi timeout, lỗi và kết quả không rõ đã được xác định chưa? |

Không phải mọi cạnh trực tiếp đều là lỗi. Một ứng dụng CRUD nhỏ có thể cho phép presentation gọi một query service đơn giản nếu đó là quyết định có chủ đích. Một domain module cũng có thể phụ thuộc một thư viện thuần Java hữu ích. Đánh giá phải dựa trên rủi ro thay đổi, mức độ ghép nối và yêu cầu của hệ thống, không dựa vào việc áp dụng máy móc một sơ đồ duy nhất.

### Chu trình phụ thuộc

Giả sử:

~~~mermaid
flowchart LR
    A["application"] --> D["domain"]
    D --> I["infrastructure"]
    I --> A
~~~

Chu trình này khiến ba package khó thay đổi độc lập. Ví dụ domain import một repository implementation trong infrastructure, còn infrastructure lại triển khai một interface của application. Cần xác định hợp đồng thuộc về phía nào và chuyển tham chiếu cụ thể ra khỏi domain. Nếu domain cần khả năng lưu/tải, có thể định nghĩa port tại domain hoặc application tùy ngôn ngữ và trách nhiệm sở hữu; adapter hạ tầng triển khai port đó.

Chu trình ở package graph cũng có thể do một class tiện ích đặt sai package. Đừng chỉ xóa cạnh để làm đẹp sơ đồ; hãy xác định lý do phụ thuộc và chuyển trách nhiệm hoặc hợp đồng đến nơi hợp lý.

## 7. Dùng fan-in, fan-out và mức độ thay đổi như tín hiệu

- **Fan-in** là số thành phần phụ thuộc vào một thành phần. Fan-in cao có thể cho thấy một hợp đồng dùng chung có giá trị, nhưng cũng có nghĩa thay đổi thành phần đó có phạm vi ảnh hưởng lớn.
- **Fan-out** là số thành phần mà một thành phần phụ thuộc vào. Fan-out cao có thể cho thấy một lớp điều phối quá nhiều chi tiết hoặc một module biết quá nhiều về các phần khác.
- **Chu trình phụ thuộc** cho thấy các nhóm thành phần không thể sắp xếp thành thứ tự phụ thuộc rõ ràng và thường khó tách khi build/test.
- **Độ tập trung thay đổi** cho biết một yêu cầu thường làm thay đổi bao nhiêu lớp, package hoặc module. Nếu một thay đổi chính sách làm sửa cả controller, entity ORM, mapper và nhiều adapter, có thể có ranh giới chưa đúng.

Không nên dùng một ngưỡng số lượng fan-in/fan-out làm chuẩn chung cho mọi dự án. Một interface domain được nhiều adapter dùng có thể có fan-in cao nhưng vẫn ổn định. Một lớp facade có fan-out lớn có thể là điểm điều phối có chủ đích. Các con số chỉ là tín hiệu để đặt câu hỏi, cần kết hợp với kịch bản thay đổi và lịch sử sửa đổi.

Một cách hữu ích là ghi nhận mỗi kịch bản: số package cần sửa, số module bị ảnh hưởng, các test cần cập nhật và các hợp đồng bên ngoài thay đổi. Qua nhiều thay đổi, nhóm có thể thấy ranh giới nào thường xuyên gây lan truyền chỉnh sửa.

## 8. Biến quy tắc kiến trúc thành kiểm thử tự động

Sau khi thống nhất hướng phụ thuộc mong muốn, hãy biến quy tắc quan trọng thành kiểm thử để ngăn vi phạm mới. ArchUnit cho phép kiểm tra phụ thuộc package trong Java.

Ví dụ: domain không được phụ thuộc presentation hoặc infrastructure; application không được phụ thuộc trực tiếp infrastructure:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class LayerDependencyTest {

    @ArchTest
    static final ArchRule domainDoesNotDependOnOuterLayers =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..presentation..",
                "..infrastructure.."
            );

    @ArchTest
    static final ArchRule applicationDoesNotDependOnInfrastructure =
        noClasses()
            .that().resideInAPackage("..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("..infrastructure..");
}
~~~

Các rule trên giả định package thực tế có cấu trúc tương ứng và test source đã có dependency ArchUnit. Có thể bổ sung rule cho adapter, controller hoặc module khác theo kiến trúc của dự án. Hãy điều chỉnh pattern package chính xác; rule quá rộng hoặc quá hẹp có thể tạo kết quả sai.

ArchUnit kiểm tra phụ thuộc mã nguồn/bytecode ở mức nó hỗ trợ. Nó không chứng minh timeout của HTTP client đã cấu hình đúng, bean nào được chọn ở production, message schema tương thích hoặc service có thể triển khai độc lập. Những điều đó cần test cấu hình, contract test, integration test và quan sát runtime tương ứng.

Có thể kiểm tra module dependency ở build bằng Gradle/Maven và đưa rule vào CI. Mục tiêu là để vi phạm hướng phụ thuộc được phát hiện ngay khi có thay đổi, thay vì chờ tới lúc refactor lớn hoặc deploy.

## 9. Đánh giá cả cấu trúc dữ liệu và hợp đồng bên ngoài

Đồ thị class/package chưa thể hiện đầy đủ các phụ thuộc được tạo bởi dữ liệu và hợp đồng. Ví dụ:

- Domain dùng enum có cùng thứ tự với cột ordinal trong database; đổi thứ tự enum có thể làm dữ liệu cũ đổi nghĩa.
- API response trả trực tiếp JPA entity; đổi quan hệ hoặc lazy loading có thể làm hợp đồng bên ngoài thay đổi.
- Một message consumer phụ thuộc tên field hoặc ý nghĩa của event do service khác phát.
- Nhiều service cùng ghi một bảng; thay đổi schema có thể buộc triển khai đồng thời.
- Một truy vấn báo cáo phụ thuộc vào view hoặc stored procedure mà nhóm application không nhìn thấy trong class graph.

Khi review, hãy hỏi thêm ai sở hữu schema và hợp đồng, phiên bản nào đang được dùng, cách thay đổi tương thích ngược và liệu có thể triển khai theo từng bước hay không. Những phụ thuộc này có thể không xuất hiện trong import graph nhưng vẫn quyết định phạm vi ảnh hưởng.

## 10. Mẫu ghi nhận kết quả review

Một đánh giá có thể được ghi ngắn gọn theo mẫu sau:

| Mục | Nội dung cần ghi |
|---|---|
| Kịch bản | Ví dụ: đổi database nhưng giữ nguyên hành vi đặt hàng. |
| Kết quả mong đợi | Chỉ persistence adapter, mapping, migration và integration test cần thay đổi. |
| Đồ thị quan sát | Application import JPA repository implementation; domain tham chiếu kiểu Hibernate. |
| Sai lệch | Hợp đồng lưu trữ và kiểu ORM đã rò vào tầng bên trong. |
| Tác động | Thay database buộc sửa ca sử dụng và domain, tăng chi phí kiểm thử. |
| Hướng điều chỉnh | Định nghĩa port ở application/domain; adapter hạ tầng triển khai; mapper chuyển domain sang persistence entity. |
| Bằng chứng sau sửa | ArchUnit rule pass, domain/application test không đổi, repository integration test pass trên engine mục tiêu. |

Đánh giá nên phân biệt sự kiện quan sát được với giả định. Ví dụ “application import JpaRepository” là bằng chứng cụ thể; “việc này sẽ khiến mọi thay đổi database lan tới domain” là nhận định cần kiểm tra bằng kịch bản và cấu trúc thực tế. Nếu một ranh giới được cố ý nới lỏng để đơn giản hóa CRUD, hãy ghi rõ lý do, phạm vi và điều kiện cần xem xét lại.

## 11. Quy trình review thiết kế bằng thay đổi và đồ thị

Khi review một ứng dụng phân tầng, hãy đi theo trình tự:

1. **Chọn một số kịch bản thay đổi có khả năng xảy ra.** Bao gồm thay đổi API, chính sách nghiệp vụ, kênh giao tiếp, công nghệ lưu trữ và tích hợp ngoài.
2. **Nêu trước phạm vi thay đổi mong muốn.** Thành phần nào nên thay đổi, thành phần nào cần giữ ổn định và vì sao?
3. **Thu thập đồ thị phụ thuộc thực tế.** Kết hợp import/type reference, module dependency, DI wiring, runtime trace và hợp đồng dữ liệu.
4. **Lần theo đường lan truyền.** Từ điểm thay đổi, đi qua các cạnh để xác định những lớp/module cần sửa và các phụ thuộc ẩn.
5. **Tìm tín hiệu cấu trúc.** Kiểm tra chu trình, phụ thuộc ngược, tầng bị bỏ qua, fan-in/fan-out bất thường và lớp có nhiều lý do thay đổi.
6. **Đối chiếu với test.** Xác định test nào chứng minh domain, application, adapter và hợp đồng ngoài vẫn đúng.
7. **Đề xuất điều chỉnh nhỏ nhất có ích.** Chuyển port, tách mapper, gom trách nhiệm hoặc tạo adapter khi điều đó làm giảm lan truyền thay đổi có thể chứng minh.
8. **Tự động hóa quy tắc quan trọng.** Dùng ArchUnit, build rule hoặc contract test để bảo vệ ranh giới trong CI.
9. **Đánh giá lại bằng cùng kịch bản.** Kiểm tra số thành phần bị ảnh hưởng và rủi ro còn lại sau thay đổi.

Một thiết kế phân tầng tốt không được đánh giá chỉ bằng việc có đủ package hoặc tuân theo một sơ đồ mẫu. Hãy xem một yêu cầu cụ thể sẽ thay đổi phần nào, sau đó dùng đồ thị phụ thuộc thực tế để giải thích vì sao thay đổi lan tới những phần đó. Khi các ranh giới phù hợp với lý do thay đổi, phụ thuộc có hướng rõ ràng và được kiểm thử tự động, hệ thống sẽ dễ bảo trì hơn mà không cần tách tầng hoặc module một cách hình thức.

