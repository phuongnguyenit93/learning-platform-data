# Tự đánh giá bằng package tree và verification evidence

Trước khi gửi một thiết kế modular monolith đi review, nhóm phát triển có thể tự kiểm tra phần lớn rủi ro cấu trúc bằng hai nguồn bằng chứng: **package tree** và **kết quả verification**. Package tree cho thấy code được tổ chức thành những vùng nào, package nào có vẻ là API và package nào chứa implementation nội bộ. Verification của Spring Modulith phân tích các application module đã phát hiện và báo các dependency vi phạm quy tắc kiến trúc.

Hai nguồn này bổ sung cho nhau. Package tree giúp người review hiểu cấu trúc và đặt câu hỏi về ranh giới. Verification giúp xác nhận một số quy tắc dependency, cycle và encapsulation trên các class được phân tích. Tuy nhiên, một package tree trông gọn hoặc một test verification pass chưa đủ chứng minh thiết kế tốt. Nhóm vẫn phải kiểm tra ownership nghiệp vụ, contract, transaction, event và dữ liệu.

Trong SPRING_MODULITH_MODULE_MODEL, bài học này cung cấp quy trình tự đánh giá có thể lặp lại: thu thập package tree, xác định module và API, đối chiếu dependency metadata, chạy architecture verification, phân loại bằng chứng, ghi findings và chuẩn bị một báo cáo ngắn có thể chuyển cho reviewer.

## 1. Mục tiêu của tự đánh giá

Sau khi hoàn thành, bạn có thể:

- Đọc package tree để nhận diện application module và package nội bộ.
- Đối chiếu cấu trúc package với package metadata.
- Xác định public API package, Named Interface và internal package.
- Tìm dependency đáng chú ý từ imports và package references.
- Hiểu kết quả ApplicationModules.verify().
- Phân biệt bằng chứng cấu trúc với bằng chứng hành vi.
- Ghi lại violation, vị trí, consumer, provider và mức ảnh hưởng.
- Tạo checklist và báo cáo self-review trước khi gửi design review.

Mục tiêu không phải chấm điểm code bằng số lượng package hoặc số lượng violation. Mục tiêu là chứng minh các quyết định về module boundary bằng bằng chứng có thể kiểm tra lại.

## 2. Hai nguồn bằng chứng chính

### Package tree

Package tree là ảnh chụp cấu trúc source package tại một thời điểm. Nó giúp trả lời:

- Có những package gốc nào dưới application package?
- Package nào có vẻ là một capability nghiệp vụ?
- Module có package internal riêng không?
- Có package shared, common hoặc util quá rộng không?
- API và implementation có được đặt ở vị trí dễ phân biệt không?
- Có package con nào được công bố như Named Interface không?

Package tree là bằng chứng về cách code được tổ chức. Nó không tự chứng minh dependency nào đang được dùng, vì một package có thể import type từ package khác mà cây thư mục không thể hiện.

### Verification evidence

Verification evidence là kết quả kiểm tra cấu trúc application module bằng Spring Modulith, thường thông qua:

~~~java
ApplicationModules.of(ShopApplication.class).verify();
~~~

Kết quả giúp xác nhận những quy tắc mà Spring Modulith đang kiểm tra trên các module được phát hiện, chẳng hạn:

- Không có dependency cycle giữa application module.
- Module không truy cập package nội bộ chưa được expose của module khác.
- Các dependency được khai báo qua allowedDependencies được tuân thủ.
- Các additional verification đang được cấu hình cũng có thể được thực thi.

Verification là bằng chứng về những quy tắc cụ thể đã chạy. Nó không tự đánh giá business cohesion, chất lượng tên module, semantics của API hoặc tính tương thích dữ liệu.

## 3. Thu thập package tree đúng phạm vi

Trước khi tự review, xác định package gốc của ứng dụng. Ví dụ:

~~~text
com.acme.shop
~~~

Một package tree minh họa:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java
│   ├── InventoryAvailability.java
│   ├── InventoryReservation.java
│   ├── events
│   │   ├── package-info.java
│   │   └── StockReserved.java
│   └── internal
│       ├── DefaultInventoryAvailability.java
│       └── InventoryRepository.java
├── order
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── internal
│       ├── PlaceOrderService.java
│       └── OrderRepository.java
└── catalog
    ├── package-info.java
    ├── ProductCatalog.java
    └── internal
        └── ProductRepository.java
~~~

Đây là ví dụ về cấu trúc source. Khi tự đánh giá dự án thật:

1. Chọn đúng source root của ứng dụng.
2. Ghi nhận package gốc chứa lớp Spring Boot application.
3. Liệt kê package con trực tiếp.
4. Mở rộng các package module để nhìn thấy API, Named Interface và internal.
5. Đối chiếu khai báo package trong source nếu tên folder và package declaration không trùng nhau.
6. Ghi lại thời điểm hoặc commit mà package tree đại diện.

Không gộp package của test source vào package tree production mà không ghi rõ. Test fixture có thể mô phỏng module hoặc package mà production code không có.

## 4. Xác định module từ package tree

Với cấu hình mặc định, Spring Modulith phát hiện application module từ các package con trực tiếp của package gốc ứng dụng. Trong ví dụ trên, inventory, order và catalog là các module ứng viên.

Tự hỏi:

- Mỗi package cấp một có đại diện cho một capability nghiệp vụ không?
- Có package cấp một chỉ chứa lớp dùng chung mà không có ownership rõ không?
- Một capability có bị chia thành nhiều module chỉ vì framework hoặc loại class không?
- Có nhiều trách nhiệm không liên quan bị gom vào cùng một module không?
- Có package nằm ngoài package gốc khiến nhóm nghĩ nó được Spring Modulith phát hiện nhưng thực tế không phải vậy không?

Ví dụ, cấu trúc sau thường là dấu hiệu cần điều tra:

~~~text
com.acme.shop
├── controller
├── service
├── repository
├── entity
└── util
~~~

Đây là cách chia theo technical layer. Nó không cho thấy rõ module nghiệp vụ nào sở hữu use case, dữ liệu và API. Có thể các class của order, inventory và catalog bị trộn trong cùng package service hoặc repository.

Một cách tổ chức theo capability thường dễ review hơn:

~~~text
com.acme.shop
├── order
│   ├── api
│   └── internal
├── inventory
│   ├── api
│   └── internal
└── catalog
    ├── api
    └── internal
~~~

Tên package cụ thể có thể khác, nhưng mỗi module cần có trách nhiệm và ownership đủ rõ để giải thích.

## 5. Phân biệt package gốc, Named Interface và internal package

Trong module đóng, package gốc thường là API package mặc định. Package con không tự động trở thành API chỉ vì class bên trong được khai báo public. Một package con có thể được công bố có chủ đích bằng Named Interface.

Ví dụ:

~~~text
inventory
├── InventoryAvailability.java
├── events
│   ├── package-info.java
│   └── StockReserved.java
└── internal
    ├── DefaultInventoryAvailability.java
    └── InventoryRepository.java
~~~

Tự đánh dấu:

| Package/type | Vai trò dự kiến | Câu hỏi review |
|---|---|---|
| inventory | API package mặc định | Có chỉ chứa contract cần cho consumer không? |
| inventory.events | Named Interface nếu được đánh dấu | Consumer nào cần event contract? |
| inventory.internal | Implementation nội bộ | Có module ngoài nào import package này không? |
| InventoryAvailability | Public API | Contract có ổn định và đúng capability không? |
| InventoryRepository | Persistence implementation | Có bị lộ ra ngoài module không? |

Mở package-info.java để xác nhận metadata. Đừng chỉ suy luận từ tên folder events hoặc internal. Folder tên internal không tự đảm bảo Spring Modulith nhận diện mọi thứ đúng nếu package declaration hoặc module configuration khác với giả định.

## 6. Đọc package-info.java như bằng chứng kiến trúc

Package metadata giúp xác định module identity, display name, allowed dependencies và Named Interfaces.

Ví dụ module inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Named Interface events:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.inventory.events;
~~~

Module order giới hạn dependency:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order",
        displayName = "Order Processing",
        allowedDependencies = { "inventory", "catalog" }
)
package com.acme.shop.order;
~~~

Khi review, ghi lại:

- Module identifier của provider.
- Display name để người đọc nhận biết capability.
- Các dependency được cho phép.
- Named Interface nào được expose.
- Metadata có nhất quán với package tree và imports thực tế không.

Nếu không khai báo allowedDependencies, không nên tự kết luận rằng mọi dependency đã được giới hạn bằng whitelist. Hãy phân biệt quy tắc cốt lõi về cycle/encapsulation với dependency policy được khai báo tường minh.

## 7. Tìm dependency từ package tree và source references

Package tree cho biết vị trí package, còn source references cho biết module nào đang phụ thuộc vào module nào.

Ví dụ:

~~~text
order.internal.PlaceOrderService
  imports inventory.InventoryAvailability
  imports catalog.ProductCatalog

inventory.internal.DefaultInventoryAvailability
  imports inventory.internal.InventoryRepository

reporting.StockReport
  imports inventory.internal.InventoryRepository
~~~

Hai dependency đầu có thể phù hợp với API công bố. Dependency từ reporting tới inventory.internal.InventoryRepository là dấu hiệu vi phạm encapsulation cần điều tra.

Trong quá trình self-review:

1. Chọn một consumer class trong mỗi module.
2. Ghi lại các import thuộc module khác.
3. Xác định import trỏ tới package gốc, Named Interface hay package con internal.
4. So sánh dependency thực tế với allowedDependencies.
5. Xác định dependency có cần thiết về nghiệp vụ hay chỉ là tiện lợi kỹ thuật.

Không coi mọi import đều là dependency giữa module. Import JDK, Spring Framework hoặc thư viện bên ngoài không phải module dependency trong application module graph.

## 8. Đánh giá chiều dependency và chu kỳ

Một modular monolith có thể có dependency giữa các module, nhưng dependency cycle làm ranh giới khó hiểu và khó thay đổi.

Ví dụ đồ thị mong muốn:

~~~mermaid
flowchart LR
    O["order"] --> I["inventory"]
    O --> C["catalog"]
    I --> C
~~~

Đồ thị có chu kỳ:

~~~mermaid
flowchart LR
    O["order"] --> I["inventory"]
    I --> C["catalog"]
    C --> O
~~~

Khi đọc dependency:

- Xác định consumer và provider cho từng cạnh.
- Kiểm tra chiều dependency có phù hợp ownership nghiệp vụ không.
- Tìm module chỉ được tạo ra để né cycle bằng cách chuyển class qua lại.
- Xem dependency có thể thay bằng API ổn định hoặc event hay không.
- Không thay synchronous command bằng event nếu consumer cần kết quả ngay.

Một đồ thị không có cycle vẫn có thể thiết kế kém nếu một module phụ thuộc vào quá nhiều module hoặc module provider trở thành nơi chứa mọi thứ. Hãy xem cả độ rộng và ý nghĩa của dependency.

## 9. Chạy module verification trong test

Đặt architecture test trong test source của ứng dụng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test gọi verify() để xác nhận cấu trúc module theo các verification đang áp dụng. Khi có violation, test thất bại và diagnostic cho biết dependency hoặc package access cần xem xét.

Kết quả test pass là bằng chứng có giá trị khi:

- Test đã thực sự được chạy trong pipeline hoặc môi trường được ghi nhận.
- Test dùng đúng application class và classpath của ứng dụng.
- Các module cần review đã được phát hiện.
- Không có filter hoặc custom options vô tình bỏ qua violation quan trọng.
- Dependency và phiên bản thư viện khớp với build đang được đánh giá.

Một file test tồn tại trong repository chưa phải verification evidence. Cần có kết quả chạy test tương ứng với commit được review.

## 10. Phân biệt verification pass và thiết kế tốt

Verification pass có nghĩa là các rule được thực thi không phát hiện violation. Nó không có nghĩa toàn bộ thiết kế đã được chứng minh đúng.

Ví dụ, cấu trúc sau có thể không tạo dependency cycle:

~~~text
com.acme.shop
├── common
│   ├── CommonService.java
│   ├── CommonRepository.java
│   └── CommonUtils.java
├── order
├── inventory
└── catalog
~~~

Nhưng module common có thể đang sở hữu quá nhiều trách nhiệm không rõ ràng. Verification không thể tự quyết định các capability đó có nên nằm cùng nhau hay không.

Tương tự:

- Module có thể tuân thủ allowedDependencies nhưng API quá rộng.
- Package internal có thể không bị truy cập nhưng module vẫn thiếu cohesion.
- Dependency graph có thể acyclic nhưng chiều dependency không hợp lý.
- Event có thể được expose đúng package nhưng payload không có contract ổn định.
- Test verification có thể pass trong khi transaction semantics bị thay đổi.

Vì vậy, package tree và verification phải được kết hợp với review nghiệp vụ và contract.

## 11. Đọc verification evidence theo từng loại violation

Khi test thất bại, phân loại lỗi trước khi đề xuất sửa:

| Loại bằng chứng/violation | Điều cần kiểm tra |
|---|---|
| Dependency cycle | Các module trong chu kỳ và chiều dependency |
| Access to internal package | Consumer, provider và package bị truy cập |
| Dependency not allowed | allowedDependencies của consumer và identifier provider |
| Named Interface reference không hợp lệ | Tên interface, package-info và module identifier |
| Additional verification failure | jMolecules/ArchUnit rule hoặc custom rule đang chạy |
| Không có violation | Xác nhận test chạy đúng app class và options |

Không sửa mọi violation bằng cách mở module hoặc thêm dependency vào whitelist. Trước hết phải xác định thiết kế có thực sự cần dependency đó không và consumer có thể dùng API phù hợp hay không.

## 12. Bằng chứng cần lưu trong self-review

Một self-review có thể được reviewer khác tái kiểm tra nếu ghi rõ nguồn và phạm vi:

| Bằng chứng | Thông tin cần lưu |
|---|---|
| Package tree | Source root, package gốc, commit hoặc thời điểm |
| Package metadata | package-info.java và annotation liên quan |
| Dependency references | Consumer, provider, import hoặc event subscription |
| Verification test | Test class và application class được phân tích |
| Test result | PASS/FAIL, số test, diagnostic liên quan |
| Dependency configuration | Phiên bản Spring Modulith và classpath liên quan |
| Additional rules | VerificationOptions, ArchUnit/jMolecules hoặc custom rules |
| Findings | Vị trí, tác động, mức độ, owner và hành động |

Không ghi “verification pass” mà thiếu test name hoặc commit. Không ghi “package tree sạch” mà không chỉ rõ package root được kiểm tra.

## 13. Xác nhận phạm vi của verification

Trước khi dùng kết quả làm bằng chứng, trả lời:

1. Application class nào được truyền vào ApplicationModules.of()?
2. Package root nào được dùng để phát hiện module?
3. Những module nào được phát hiện?
4. Test chạy trên classpath nào?
5. Có additional verification nào được bật qua classpath hoặc VerificationOptions không?
6. Có filter, ignore hoặc custom predicate nào loại violation không?
7. Kết quả có thuộc cùng commit với package tree không?

Nếu không biết phạm vi, kết quả pass có thể tạo cảm giác an toàn giả. Ví dụ, test dùng nhầm application class ở một package root khác có thể không kiểm tra module mà nhóm đang review.

## 14. So sánh package tree với verification result

Hai nguồn bằng chứng nên được đối chiếu:

| Package tree cho thấy | Verification evidence cho thấy | Nhận định |
|---|---|---|
| Có inventory/internal | order truy cập inventory.internal | Encapsulation bị vi phạm |
| Có inventory/events | order phụ thuộc inventory::events | Cần xác nhận Named Interface được khai báo và dependency được cho phép |
| Có order và inventory | Dependency cycle order ↔ inventory | Cần xem lại chiều dependency |
| Có common package rất rộng | Không có violation | Vẫn cần review ownership và cohesion |
| Có package con không rõ vai trò | Không có violation | Cần xác định API, internal hay module riêng |
| Không thấy module trong tree dự kiến | Test không báo lỗi | Kiểm tra module detection và application root |

Nếu package tree gợi ý một vấn đề nhưng verification không báo, đừng vội kết luận verification sai. Có thể vấn đề thuộc chất lượng thiết kế mà rule hiện tại không kiểm tra, hoặc class chưa nằm trong phạm vi phân tích.

## 15. Ví dụ self-review một package tree

Giả sử nhóm chuẩn bị review thay đổi module inventory:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java
│   ├── InventoryAvailability.java
│   ├── events
│   │   ├── package-info.java
│   │   └── StockReserved.java
│   └── internal
│       ├── DefaultInventoryAvailability.java
│       └── InventoryRepository.java
├── order
│   ├── package-info.java
│   └── internal
│       └── PlaceOrderService.java
└── reporting
    ├── package-info.java
    └── StockReport.java
~~~

### Nhận xét từ package tree

- inventory có API ở package gốc.
- inventory.events có vẻ là Named Interface nhưng cần mở package-info.java để xác nhận.
- inventory.internal chứa implementation và repository.
- order và reporting là các module khác.
- Chưa thể biết reporting có truy cập internal hay không chỉ bằng cây package.

### Bằng chứng dependency

Giả sử source reference cho thấy:

~~~text
order.internal.PlaceOrderService
  -> inventory.InventoryAvailability

reporting.StockReport
  -> inventory.internal.InventoryRepository
~~~

Dependency thứ nhất đi qua API package. Dependency thứ hai truy cập package internal và cần được sửa hoặc có quyết định kiến trúc rõ ràng.

### Verification result giả định

~~~text
Violation:
Module 'reporting' depends on non-exposed type
'inventory.internal.InventoryRepository'
~~~

Kết quả này phù hợp với package tree và import evidence. Nhóm có thể chuyển reporting sang một read API hoặc projection được inventory công bố thay vì dùng repository nội bộ.

Không nên thêm toàn bộ inventory.internal thành Named Interface chỉ để test pass. Làm vậy biến implementation detail thành contract và làm tăng phạm vi phụ thuộc của consumer.

## 16. Đánh giá package tree theo từng module

Với mỗi module, tự trả lời:

### Identity và ownership

- Tên module có diễn đạt capability nghiệp vụ không?
- Có owner rõ ràng cho logic và dữ liệu không?
- Module có đang chứa nhiều capability không liên quan không?
- Có class nào chỉ tồn tại vì cấu trúc technical layer cũ không?

### API và encapsulation

- Package gốc chứa những contract nào?
- Named Interface có cần thiết và được khai báo đúng không?
- Package internal có thực sự được giữ nội bộ không?
- API có lộ repository, entity persistence hoặc framework type không cần thiết không?

### Dependency

- Consumer nào phụ thuộc vào module?
- Dependency có được khai báo rõ khi cần whitelist không?
- Có cycle hoặc dependency ngược chiều không?
- Có module nào trở thành dependency trung tâm cho mọi capability không?

### Khả năng thay đổi

- Có thể thay implementation mà không đổi consumer không?
- Có thể kiểm thử module độc lập ở mức phù hợp không?
- Có event hoặc API contract rõ khi consumer cần tương tác không?
- Có migration path nếu cần thay đổi public API không?

## 17. Dùng trạng thái PASS, NEEDS EVIDENCE và ACTION REQUIRED

Không nên chỉ dùng một điểm số tổng hợp. Hãy ghi trạng thái theo từng finding:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| PASS | Có bằng chứng cho thấy tiêu chí được đáp ứng | Lưu evidence và tiếp tục |
| NEEDS EVIDENCE | Chưa đủ dữ liệu để kết luận | Thu thập package metadata, references hoặc test result |
| ACTION REQUIRED | Có vấn đề cụ thể đã được xác nhận | Tạo finding, owner và hành động |
| ACCEPTED RISK | Rủi ro được chấp nhận có lý do và người chịu trách nhiệm | Ghi phạm vi, thời hạn review và điều kiện kết thúc |

Ví dụ:

| Tiêu chí | Trạng thái | Bằng chứng/ghi chú |
|---|---|---|
| Module inventory có identity rõ | PASS | package-info.java có id inventory |
| API package được xác định | PASS | InventoryAvailability ở package gốc |
| reporting không truy cập internal | ACTION REQUIRED | Import InventoryRepository trong StockReport |
| Không có dependency cycle | PASS | ApplicationModules.verify() pass phần cycle |
| Event contract ổn định | NEEDS EVIDENCE | Chưa có consumer contract test |

Trạng thái NEEDS EVIDENCE không phải PASS. Nếu thiếu bằng chứng quan trọng, reviewer cần biết điều đó trước khi approve.

## 18. Ghi finding có thể hành động

Một finding tốt gồm:

- **Vị trí:** package, class hoặc metadata.
- **Bằng chứng:** package tree, import, diagnostic hoặc test.
- **Tác động:** dependency, encapsulation hoặc contract nào bị ảnh hưởng.
- **Hành động:** thay đổi cụ thể cần thực hiện.
- **Owner:** người hoặc nhóm chịu trách nhiệm.
- **Điều kiện đóng:** bằng chứng nào xác nhận đã sửa.

Ví dụ:

~~~text
Finding: reporting truy cập repository nội bộ của inventory

Vị trí:
reporting.StockReport
inventory.internal.InventoryRepository

Bằng chứng:
Source reference cho thấy reporting import InventoryRepository.
ApplicationModules.verify() báo dependency tới non-exposed type.

Tác động:
reporting phụ thuộc trực tiếp persistence implementation của inventory.
Inventory không thể thay repository mà không ảnh hưởng consumer.

Hành động:
Cung cấp read API hoặc projection phù hợp cho reporting.
Chuyển StockReport sang contract được công bố.

Điều kiện đóng:
Không còn import inventory.internal từ reporting.
Architecture verification pass trên cùng commit.
~~~

Tránh finding chung như “cần cải thiện module boundary”. Hãy chỉ ra chính xác consumer, provider và reference gây vấn đề.

## 19. Những giới hạn của package tree và verification evidence

Hai nguồn bằng chứng này không bao phủ toàn bộ hệ thống.

| Điều chưa được chứng minh | Bằng chứng bổ sung nên có |
|---|---|
| Business cohesion của module | Use case map, domain model, review với owner |
| API có giữ semantics không | Characterization và contract tests |
| Event consumer hiểu payload không | Serialization/schema compatibility test |
| Transaction có đúng không | Integration test và transaction scenario |
| Data ownership có được tuân thủ không | Repository/query inventory, database access review |
| HTTP client có tương thích không | OpenAPI diff và consumer contract test |
| Configuration có được bind không | Configuration metadata và context test |
| Runtime behavior có ổn định không | Log, metric, trace và deployment observation |
| Consumer ngoài source tree còn tồn tại không | Integration inventory và owner confirmation |

Package tree có thể bỏ sót dependency phát sinh qua reflection, configuration hoặc external integration. Verification cũng chỉ kiểm tra những gì nằm trong phạm vi module model và rule đang chạy.

## 20. Quy trình tự đánh giá trước design review

Thực hiện theo trình tự:

1. **Chốt phạm vi:** ghi commit, application class và source root.
2. **Thu thập package tree:** lấy package tree của production source.
3. **Đánh dấu module:** xác định module gốc, identifier và display name.
4. **Đọc metadata:** kiểm tra @ApplicationModule, allowedDependencies và Named Interface.
5. **Đánh dấu API/internal:** xác định contract và implementation.
6. **Lập dependency list:** ghi consumer, provider và package/type được tham chiếu.
7. **Chạy architecture verification:** lưu test name và kết quả thuộc đúng commit.
8. **Phân loại violation:** cycle, internal access, dependency policy hoặc additional rule.
9. **Đối chiếu evidence:** xác nhận package tree, source reference và diagnostic có nhất quán.
10. **Đánh giá giới hạn:** ghi rõ contract hoặc runtime behavior chưa được kiểm chứng.
11. **Tạo findings:** mỗi finding có bằng chứng, tác động, owner và điều kiện đóng.
12. **Chuẩn bị báo cáo:** chuyển trạng thái PASS, NEEDS EVIDENCE, ACTION REQUIRED hoặc ACCEPTED RISK.

Không sửa package tree chỉ để làm sơ đồ đẹp. Nếu cấu trúc hiện tại không phù hợp, hãy ghi lại lý do và thay đổi đề xuất trước khi thực hiện refactor.

## 21. Checklist tự đánh giá

### Phạm vi và cấu trúc

- [ ] Đã xác định đúng application package và application class.
- [ ] Package tree thuộc đúng source root và commit.
- [ ] Các package con trực tiếp đã được phân loại thành module hoặc package phụ trợ.
- [ ] Tên module phản ánh capability nghiệp vụ.
- [ ] Không có package shared/common/util quá rộng chưa được giải thích.

### API và encapsulation

- [ ] Đã đọc package-info.java của module.
- [ ] Đã xác định module identifier và display name.
- [ ] Đã đánh dấu API package và Named Interface.
- [ ] Đã xác định internal package.
- [ ] Consumer không truy cập implementation nội bộ ngoài ý muốn.

### Dependency và verification

- [ ] Đã liệt kê consumer/provider và import liên module.
- [ ] Đã kiểm tra allowedDependencies nếu module dùng whitelist.
- [ ] Đã kiểm tra Named Interface reference.
- [ ] Architecture test gọi đúng application class.
- [ ] Test đã chạy và kết quả thuộc đúng commit.
- [ ] Không có filter hoặc ignore che violation ngoài ý muốn.
- [ ] Các violation đã được phân loại theo nguồn.

### Chất lượng bằng chứng

- [ ] Package tree và verification result nhất quán.
- [ ] Finding có vị trí và diagnostic/source reference.
- [ ] Test bổ sung được chọn cho contract, data và behavior khi cần.
- [ ] Các phần NEEDS EVIDENCE được ghi rõ.
- [ ] Mỗi ACTION REQUIRED có owner và điều kiện đóng.
- [ ] ACCEPTED RISK có lý do và thời hạn review.

## 22. Mẫu báo cáo self-review

~~~markdown
# Modular Design Self-Review

## Scope
- Commit:
- Application class:
- Application package:
- Source root:

## Package tree
<Dán package tree hoặc đường dẫn tới artifact>

## Module inventory
| Module package | Identifier | Display name | Public API | Named Interfaces |
|---|---|---|---|---|

## Dependency review
| Consumer | Provider | Referenced package/API | Allowed? | Evidence |
|---|---|---|---|---|

## Verification
- Test class:
- Application class:
- Result:
- Additional rules/options:
- Diagnostic:

## Findings
| Status | Finding | Evidence | Impact | Owner | Exit criteria |
|---|---|---|---|---|---|

## Evidence gaps
- 

## Self-review decision
<Ready for review / Ready with accepted risks / Needs changes>
~~~

## 23. Kết luận

Package tree giúp nhìn thấy cấu trúc module, vị trí API và implementation nội bộ. Verification evidence giúp xác nhận các quy tắc dependency, cycle và encapsulation mà Spring Modulith đang kiểm tra. Khi đối chiếu hai nguồn này, nhóm có thể phát hiện package được tổ chức chưa hợp lý, consumer truy cập internal package, dependency policy chưa đúng hoặc phạm vi verification chưa đầy đủ.

Một kết quả verify pass chỉ chứng minh các rule đã chạy không tìm thấy violation trong phạm vi được kiểm tra. Nó không chứng minh business cohesion, API semantics, event compatibility, transaction, data ownership hoặc runtime behavior. Hãy bổ sung contract và integration evidence theo rủi ro, ghi findings có thể hành động và nêu rõ phần chưa có bằng chứng. Một self-review tốt giúp design reviewer tái kiểm tra được package tree, test result, phạm vi phân tích và quyết định kiến trúc trên cùng một commit.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
