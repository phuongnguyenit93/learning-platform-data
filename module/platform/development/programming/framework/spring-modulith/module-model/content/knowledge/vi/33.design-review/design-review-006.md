# Quyết định có nên dùng open module

Khi đưa Spring Modulith vào một ứng dụng legacy, nhóm có thể phát hiện nhiều module đang tham chiếu trực tiếp các lớp nằm trong package con của module khác. Đóng tất cả những package đó ngay lập tức có thể đòi hỏi nhiều lần refactor và tạo rủi ro cho một hệ thống đang hoạt động. Spring Modulith cung cấp kiểu application module OPEN để hỗ trợ quá trình chuyển đổi từng bước.

Quyết định dùng OPEN cần được xem như một lựa chọn kiến trúc có chủ đích. Nó giúp mô hình hóa một module legacy mà các package nội bộ vẫn đang được nhiều module khác sử dụng, nhưng đồng thời làm yếu đi việc kiểm soát encapsulation và một phần kiểm tra dependency cycle. Với module mới hoặc module đã có API ổn định, kiểu CLOSED mặc định thường là lựa chọn phù hợp hơn.

## 1. OPEN thay đổi điều gì trong mô hình module?

Spring Modulith xem một application module là đơn vị có API cung cấp, phần triển khai nội bộ và các dependency mà module cần từ nơi khác. Với module CLOSED, chỉ package gốc và các named interface được công khai mới là bề mặt API cho module khác sử dụng. Các package con còn lại được xem là nội bộ.

Ví dụ module inventory:

~~~text
com.example
├── Application.java
├── inventory
│   ├── InventoryManagement.java
│   ├── api
│   │   ├── package-info.java
│   │   └── StockAvailability.java
│   └── internal
│       ├── StockRepository.java
│       └── StockPolicy.java
└── shipping
    └── ShippingService.java
~~~

Trong module CLOSED, shipping có thể phụ thuộc vào InventoryManagement ở package gốc hoặc StockAvailability nếu package api được đánh dấu bằng @NamedInterface. Việc import StockRepository hoặc StockPolicy từ inventory.internal sẽ bị Spring Modulith xem là vi phạm ranh giới module.

Với module OPEN, Spring Modulith thay đổi cách xác minh:

- Việc truy cập các kiểu nội bộ của module từ module khác nhìn chung được cho phép.
- Các kiểu trong package gốc và package con được đưa vào unnamed named interface, trừ những kiểu đã được gán rõ vào named interface.
- Module OPEN bị loại khỏi thuật toán phát hiện dependency cycle.

Như vậy, OPEN nới lỏng việc đóng gói ở cấp application module. Nó không thay đổi quy tắc visibility của Java, không tự tạo Spring bean và không tự thay đổi component scanning.

## 2. Khai báo module OPEN

Kiểu application module mặc định là CLOSED. Để chuyển module inventory thành OPEN, khai báo annotation trong package-info.java ở package gốc:

~~~java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.inventory;
~~~

Nếu package-info.java đã có allowedDependencies hoặc displayName, giữ các thuộc tính đó trong cùng một annotation:

~~~java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.OPEN,
        displayName = "Quản lý tồn kho",
        allowedDependencies = "orders"
)
package com.example.inventory;
~~~

Chỉ dùng một khai báo @ApplicationModule cho package. Hãy kết hợp các thuộc tính cần thiết thay vì tạo nhiều package annotation cạnh tranh nhau.

Có thể kiểm tra kiểu module trong mô hình:

~~~java
var modules = ApplicationModules.of(Application.class);

var inventory = modules.getModuleByName("inventory")
        .orElseThrow();

System.out.println(inventory.isOpen());
~~~

Đoạn mã minh họa cách xem module có được nhận diện là OPEN hay không. Hãy dùng API phù hợp với phiên bản Spring Modulith đang được quản lý trong dự án.

## 3. OPEN không phải là một API được thiết kế tốt

Khi module OPEN, các kiểu trong sub-package của nó được xem là thuộc unnamed named interface nếu chúng chưa được gán vào named interface cụ thể. Điều này cho phép consumer tham chiếu các kiểu công khai ở nhiều package bên trong module.

Ví dụ, shipping có thể đang inject trực tiếp một lớp nội bộ:

~~~java
package com.example.shipping;

import com.example.inventory.internal.StockRepository;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final StockRepository stockRepository;

    ShippingService(StockRepository stockRepository) {
        this.stockRepository = stockRepository;
    }
}
~~~

Khi inventory là CLOSED, tham chiếu đến StockRepository là vi phạm encapsulation của application module. Nếu inventory được chuyển thành OPEN, kiểm tra truy cập package nội bộ có thể chấp nhận tham chiếu này, miễn là kiểu và thành viên được Java cho phép truy cập.

Điều đó không có nghĩa StockRepository đã trở thành hợp đồng nghiệp vụ tốt. Consumer vẫn phụ thuộc vào persistence model, truy vấn dữ liệu và cách triển khai của inventory. Nếu repository đổi hoặc dữ liệu được tổ chức lại, shipping có thể phải thay đổi theo.

OPEN giúp một hệ thống legacy được mô hình hóa trong giai đoạn chuyển đổi. Nó không tự giải quyết coupling đã tồn tại.

## 4. Phân biệt OPEN với allowedDependencies

Hai cấu hình này giải quyết hai câu hỏi khác nhau:

| Cấu hình | Câu hỏi được trả lời | Tác động |
|---|---|---|
| type = OPEN | Module cung cấp có che giấu các package nội bộ với consumer không? | Cho phép tham chiếu các kiểu nội bộ theo quy tắc xác minh của OPEN |
| allowedDependencies | Module tiêu thụ được phép phụ thuộc vào những module nào? | Giới hạn các module mà consumer được phép tham chiếu |

Ví dụ, inventory được khai báo OPEN:

~~~java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.inventory;
~~~

Module shipping vẫn có thể tự giới hạn dependency của nó:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory"
)
package com.example.shipping;
~~~

Trong ví dụ này, OPEN nới lỏng việc truy cập package nội bộ của inventory. allowedDependencies trên shipping vẫn giới hạn module mà shipping được phép phụ thuộc vào. Nếu shipping khai báo chỉ cho phép orders, việc phụ thuộc vào inventory vẫn bị từ chối theo allowlist, dù inventory là OPEN.

Vì vậy, không nên dùng OPEN như một cách bỏ qua mọi quy tắc dependency. Hãy xem riêng encapsulation của provider và allowlist của consumer.

## 5. Đánh giá tác động đến kiểm tra kiến trúc

Spring Modulith verification kiểm tra nhiều quy tắc, trong đó có phụ thuộc vòng, truy cập API module và allowedDependencies. OPEN tác động trực tiếp đến một số kiểm tra này.

| Quy tắc | Module CLOSED | Module OPEN |
|---|---|---|
| Truy cập package nội bộ từ module khác | Bị từ chối | Được cho phép nói chung |
| Kiểu trong package con được công khai | Cần named interface phù hợp | Được đưa vào unnamed named interface nếu chưa thuộc named interface khác |
| Kiểm tra dependency allowlist của consumer | Vẫn áp dụng nếu consumer khai báo | Vẫn áp dụng nếu consumer khai báo |
| Tham gia thuật toán phát hiện dependency cycle | Có | Bị loại khỏi thuật toán |

Điểm cần cân nhắc kỹ là việc loại module OPEN khỏi thuật toán cycle detection. Nếu module OPEN nằm giữa một chuỗi dependency, nhóm không còn nhận được cùng mức bảo vệ phát hiện cycle như với các module CLOSED. Vì vậy, việc bật OPEN có thể làm cho một số quan hệ phụ thuộc khó được kiểm soát hơn.

Không nên kết luận rằng toàn bộ dependency cycle trong ứng dụng đều bị bỏ qua chỉ vì có một module OPEN. Hãy đọc kết quả verify và mô hình dependency thực tế của dự án; điểm chính là module OPEN không tham gia thuật toán phát hiện cycle như module CLOSED.

## 6. Khi nào có thể chấp nhận OPEN?

OPEN có thể là quyết định chuyển tiếp hợp lý nếu một số điều kiện sau cùng tồn tại:

- Ứng dụng legacy đã có nhiều consumer phụ thuộc vào các package con của module.
- Các kiểu nội bộ được tham chiếu rộng rãi và việc chuyển tất cả consumer cùng lúc có rủi ro cao.
- Nhóm đang đưa Spring Modulith vào để lập bản đồ dependency trước khi tái cấu trúc.
- Chưa thể xác định ngay một API ổn định vì cần khảo sát use case thực tế của các consumer.
- Nhóm có kế hoạch rõ ràng để chuyển các tham chiếu nội bộ sang API hoặc named interface theo từng đợt.

Trong trường hợp này, OPEN cho phép bắt đầu quản lý module trong khi vẫn duy trì khả năng tương thích với code hiện có. Nhóm có thể ghi nhận dependency, đặt giới hạn module ở phía consumer và chuyển dần các hợp đồng mà không phải thay đổi toàn bộ ứng dụng trong một lần.

Một ví dụ phù hợp là module inventory đã được nhận diện như một module nghiệp vụ, nhưng shipping, orders và reporting đang gọi trực tiếp nhiều kiểu trong inventory.internal. Nhóm có thể tạm thời để inventory OPEN trong lúc xây dựng StockAvailability, StockReservation và các API nghiệp vụ khác.

## 7. Khi nào nên giữ CLOSED?

CLOSED nên được ưu tiên khi:

- Module mới được thiết kế và chưa có nhiều consumer legacy.
- Package gốc và named interface đã phản ánh được hợp đồng mà module muốn cung cấp.
- Consumer có thể được chuyển sang API công khai với phạm vi thay đổi chấp nhận được.
- Nhóm muốn Spring Modulith phát hiện sớm mọi tham chiếu đến package nội bộ.
- Module là phần lõi nghiệp vụ có nhiều quy tắc và dữ liệu cần được bảo vệ khỏi truy cập trực tiếp.
- Nhóm cần giữ kiểm tra dependency cycle đầy đủ cho module.

Với một modular monolith đã có ranh giới tốt, việc để module OPEN thường là dấu hiệu cần xem lại cấu trúc package. Tốt hơn là công khai đúng hợp đồng cần thiết và giữ các implementation, repository, entity trong package nội bộ.

## 8. Ma trận quyết định

Có thể dùng ma trận sau trong design review:

| Câu hỏi | Nếu câu trả lời là Có | Hướng quyết định |
|---|---|---|
| Đây là module mới hoặc đang được thiết kế lại? | Có thể định nghĩa API trước khi có consumer legacy | Ưu tiên CLOSED |
| Có nhiều consumer đang tham chiếu package nội bộ? | Đóng ngay có thể tạo đợt refactor lớn | Cân nhắc OPEN tạm thời |
| Đã biết rõ các use case mà consumer cần? | Có thể thiết kế hợp đồng nhỏ và ổn định | Ưu tiên CLOSED và named interface |
| Chưa biết hết các consumer hoặc kiểu nội bộ được dùng? | Cần khảo sát dependency trước | OPEN có thời hạn, kèm kế hoạch đo đếm |
| Cần bảo vệ dependency cycle ở cấp module? | OPEN làm giảm khả năng phát hiện cycle liên quan | Ưu tiên CLOSED |
| Không có owner hoặc mốc đóng OPEN? | Không có cơ chế kết thúc trạng thái chuyển tiếp | Không nên bật OPEN |

Một quyết định OPEN chỉ nên được chấp nhận khi nhóm có thể trả lời được ba câu hỏi: vì sao cần mở, ai chịu trách nhiệm thu hẹp, và điều kiện nào cho phép chuyển về CLOSED.

## 9. Lộ trình chuyển từ OPEN về CLOSED

Hãy coi OPEN là trạng thái chuyển tiếp có thể quan sát và có điều kiện kết thúc. Một lộ trình thực tế gồm các bước:

1. **Lập bản đồ consumer.** Dùng IDE Find Usages, tìm import và mô hình ApplicationModules để ghi nhận module nào tham chiếu package con của provider.
2. **Phân loại tham chiếu.** Tách các nhu cầu nghiệp vụ khỏi các tham chiếu kỹ thuật như repository, entity, mapper hoặc service triển khai.
3. **Thiết kế API.** Tạo interface trong package gốc hoặc named interface dành cho từng nhóm hợp đồng như api hay spi.
4. **Tạo adapter trong provider.** Giữ logic nghiệp vụ và persistence trong module sở hữu, chuyển kết quả sang kiểu API ổn định.
5. **Chuyển từng consumer.** Thay dependency vào internal bằng constructor injection qua hợp đồng công khai hoặc dùng application event nếu phù hợp với ngữ nghĩa giao tiếp.
6. **Giới hạn dependency.** Bổ sung allowedDependencies trên consumer để thể hiện rõ module hoặc named interface được phép sử dụng.
7. **Đo lại tham chiếu nội bộ.** Xác nhận không còn consumer bên ngoài sử dụng package nội bộ của provider.
8. **Đóng module.** Bỏ type = OPEN; module trở về CLOSED mặc định. Chạy lại architecture test và xử lý các vi phạm còn lại.

Ví dụ, sau khi chuyển consumer sang StockAvailability, module inventory có thể được thu hẹp về:

~~~text
com.example.inventory
├── package-info.java
├── StockAvailability.java
├── api
│   └── StockReservation.java
└── internal
    ├── StockRepository.java
    └── StockPolicy.java
~~~

Package gốc và named interface api trở thành bề mặt được công khai. Consumer không còn tham chiếu StockRepository hoặc StockPolicy.

Khi đã chuyển xong, package-info.java có thể dùng kiểu mặc định CLOSED hoặc khai báo tường minh:

~~~java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.example.inventory;
~~~

Việc bỏ thuộc tính type cũng đưa module về CLOSED vì đây là giá trị mặc định của annotation.

## 10. Kiểm chứng quyết định bằng architecture test

Tạo test để xác minh mô hình module:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Trong giai đoạn inventory còn OPEN, test có thể chấp nhận các tham chiếu đến package nội bộ của inventory. Sau khi chuyển inventory về CLOSED, các tham chiếu đó phải được thay bằng API hoặc named interface; nếu còn sót, verify() sẽ báo vi phạm.

Có thể in mô hình để xem module nào đang OPEN và các kiểu nào được nhận diện là exposed:

~~~java
var modules = ApplicationModules.of(Application.class);

modules.forEach(System.out::println);
~~~

Đầu ra mô hình giúp review module arrangement và visibility của các Spring bean. Dùng kết quả này để đối chiếu với quyết định thiết kế, nhưng không thay thế việc rà soát dependency và use case của consumer.

## 11. Ghi lại quyết định kiến trúc

Khi design review chấp thuận OPEN, ghi quyết định vào ADR hoặc tài liệu kiến trúc của dự án. Một quyết định có thể dùng mẫu sau:

~~~text
Decision: inventory is temporarily OPEN

Context:
- shipping, orders and reporting currently reference inventory sub-packages.
- Immediate encapsulation would require a broad coordinated refactor.

Reason:
- Introduce Spring Modulith verification incrementally.
- Preserve existing behavior while consumers migrate.

Risks:
- Internal package access is generally allowed.
- inventory is excluded from module cycle detection.
- Consumers may become more coupled to persistence details.

Mitigations:
- Record all external references to inventory internals.
- Introduce StockAvailability and StockReservation APIs.
- Move one consumer at a time.
- Add allowedDependencies to consumer modules where appropriate.

Owner:
- Inventory team

Exit criteria:
- No external module references inventory.internal.
- Consumers use the published API or named interfaces.
- ApplicationModules.verify() passes with inventory CLOSED.
Target review date:
- A date agreed by the owning team
~~~

Không để quyết định OPEN chỉ tồn tại trong annotation. Lý do, rủi ro và điều kiện kết thúc cần được người review và nhóm sở hữu module cùng hiểu.

## 12. Checklist cho design review

- [ ] Xác định module đang được đề xuất chuyển thành OPEN.
- [ ] Xác nhận module có nhiều consumer legacy truy cập package nội bộ.
- [ ] Liệt kê các consumer và kiểu nội bộ đang được tham chiếu.
- [ ] Giải thích vì sao chưa thể chuyển toàn bộ consumer sang API ngay.
- [ ] Đánh giá tác động đến encapsulation và cycle detection.
- [ ] Xác nhận allowedDependencies vẫn thể hiện đúng quan hệ module ở phía consumer.
- [ ] Xác định owner chịu trách nhiệm chuyển đổi.
- [ ] Ghi mốc review và điều kiện chuyển về CLOSED.
- [ ] Có architecture test để quan sát thay đổi trong dependency.
- [ ] Sau khi chuyển đổi, bỏ OPEN và xác nhận verify() thành công.

Nếu không thể xác định consumer, owner hoặc điều kiện đóng OPEN, quyết định chưa đủ thông tin để được chấp nhận như một trạng thái chuyển tiếp.

## 13. Bài tập design review

Đánh giá tình huống sau:

Một ứng dụng có module inventory, orders, shipping và reporting. Module inventory chứa StockRepository, StockPolicy và StockReservationService trong package internal. Hiện tại, cả shipping và reporting đều import StockRepository; orders gọi StockReservationService trực tiếp. Nhóm muốn đưa Spring Modulith vào trong sprint này nhưng chưa thể refactor cả ba consumer.

Hãy thực hiện:

1. Ghi nhận các dependency từ shipping, reporting và orders đến inventory.internal.
2. Xác định use case thực tế của từng consumer: kiểm tra tồn kho, đọc số lượng hay giữ hàng.
3. Đề xuất các hợp đồng công khai phù hợp, chẳng hạn StockAvailability và StockReservation.
4. Đánh giá việc đặt inventory thành OPEN tạm thời trong giai đoạn lập bản đồ và chuyển đổi.
5. Nêu rõ tác động đến kiểm tra package nội bộ và dependency cycle.
6. Xác định allowedDependencies cần thiết trên từng consumer.
7. Đề xuất thứ tự chuyển consumer sao cho mỗi thay đổi có thể review và kiểm thử độc lập.
8. Viết exit criteria để inventory trở lại CLOSED.
9. Đưa ra quyết định cuối cùng: OPEN tạm thời hay giữ CLOSED và refactor ngay, kèm lý do và rủi ro được chấp nhận.

Một bản review tốt phải chỉ rõ ai được phép truy cập hợp đồng nào, vì sao OPEN cần thiết trong bối cảnh cụ thể, rủi ro nào được chấp nhận trong thời gian chuyển đổi và bằng chứng nào chứng minh module đã sẵn sàng đóng lại.

## Tài liệu tham khảo

- [Open Application Modules – Spring Modulith Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModule.Type API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html)
- [ApplicationModule Annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
