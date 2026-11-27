# Giữ hệ thống chạy được trong từng bước

Modular hóa một hệ thống legacy cần cải thiện ranh giới kiến trúc mà vẫn duy trì khả năng phục vụ nghiệp vụ. Nếu di chuyển hàng loạt package, thay đổi API, tách dữ liệu và đổi luồng xử lý trong một lần, nhóm phát triển khó xác định thay đổi nào gây lỗi và khó khôi phục khi triển khai thất bại. Cách an toàn hơn là chia quá trình thành những bước nhỏ, mỗi bước có thể kiểm thử, review, triển khai và rollback độc lập.

Spring Modulith hỗ trợ cách tiếp cận này bằng việc mô hình hóa các application module ngay trong một ứng dụng Spring Boot. Nhóm có thể bắt đầu từ codebase hiện tại, xác định một ranh giới có ý nghĩa nghiệp vụ, công bố API của module, chuyển từng caller sang API mới và dần bảo vệ dependency bằng kiểm tra kiến trúc. Ứng dụng vẫn chạy như một deployment unit trong khi cấu trúc bên trong được cải thiện từng bước.

Trong SPRING_MODULITH_MODULE_MODEL, mục tiêu là giữ hệ thống hoạt động xuyên suốt quá trình chuyển đổi: duy trì hợp đồng đang được sử dụng, chuyển quyền sở hữu từng capability, kiểm tra dữ liệu và hành vi ở mỗi bước, đồng thời chuẩn bị đường lui trước khi triển khai.

## 1. Nguyên tắc chuyển đổi từng bước

Một bước modular hóa tốt tạo ra một thay đổi có phạm vi rõ và không để hệ thống ở trạng thái nửa hoàn tất sau khi triển khai. Mỗi bước nên trả lời được bốn câu hỏi:

1. **Hành vi nào thay đổi?** Xác định capability hoặc dependency đang được chuyển.
2. **Hợp đồng nào được giữ?** Caller cũ cần tiếp tục hoạt động ra sao?
3. **Điều gì chứng minh bước này an toàn?** Chọn test, metric và điều kiện chấp nhận.
4. **Nếu có lỗi thì quay lại thế nào?** Xác định cách rollback code, cấu hình và dữ liệu.

Các nguyên tắc quan trọng:

- Chuyển một lát cắt nghiệp vụ có đầu vào và đầu ra rõ ràng thay vì di chuyển hàng trăm lớp theo package.
- Giữ API cũ hoạt động trong thời gian caller được chuyển dần.
- Chỉ có một nơi chịu trách nhiệm ghi dữ liệu cho một nghiệp vụ tại một thời điểm.
- Mỗi bước phải giữ được khả năng build, test và deploy.
- Đặt kiểm tra kiến trúc vào CI để dependency sai không quay trở lại.
- Đo hành vi thực tế bằng log, metric và trace thay vì chỉ dựa vào việc test đã xanh.

## 2. Bắt đầu bằng baseline có thể quan sát

Trước khi thay đổi cấu trúc, cần hiểu trạng thái hiện tại. Hệ thống legacy thường có các dependency ẩn qua static utility, shared table, event nội bộ, batch job hoặc cấu hình Spring. Chỉ đọc package tree không đủ để hiểu toàn bộ luồng nghiệp vụ.

Hãy lập baseline cho capability được chọn:

| Nội dung | Cần ghi nhận |
|---|---|
| Luồng nghiệp vụ | Request/job nào kích hoạt, các bước xử lý và kết quả cuối |
| Caller | Controller, service, batch job, scheduler hoặc module đang gọi |
| Dữ liệu | Bảng được đọc/ghi, transaction boundary và khóa nghiệp vụ |
| Hợp đồng | Method, DTO, exception, event và response đang được caller sử dụng |
| Tác động bên ngoài | Email, thanh toán, broker, file hoặc API đối tác |
| Vận hành | Tỷ lệ lỗi, latency, throughput và log cần theo dõi |
| Kiểm thử | Unit test, integration test, contract test và dữ liệu mẫu hiện có |

Nếu hệ thống thiếu test, hãy viết characterization test cho hành vi hiện tại trước khi refactor. Test này ghi lại kết quả đang được hệ thống cung cấp, kể cả những quy tắc cũ chưa được tài liệu hóa. Sau đó, nhóm có thể thay đổi cấu trúc mà vẫn biết hành vi nào phải được bảo toàn.

Không cố ghi lại toàn bộ hệ thống trước khi bắt đầu. Chỉ cần baseline đủ để kiểm soát lát cắt đang chuyển và các luồng có thể bị ảnh hưởng.

## 3. Chọn một lát cắt nghiệp vụ nhỏ

Không nhất thiết bắt đầu từ module lớn nhất hoặc có nhiều class nhất. Hãy chọn một capability có ranh giới tương đối rõ, ít caller hoặc có thể tạo adapter tương thích.

Ví dụ một hệ thống bán hàng có các vùng:

~~~text
legacy application
├── customer
├── inventory
├── order
├── payment
├── reporting
└── shared
~~~

Có thể chọn kiểm tra tồn kho trước nếu:

- Quy tắc tồn kho có thể mô tả độc lập.
- Các caller có thể dùng một hợp đồng nhỏ.
- Có test xác nhận số lượng khả dụng và giữ hàng.
- Dữ liệu tồn kho có thể được xác định chủ sở hữu.
- Việc chuyển đổi không đòi hỏi thay đổi đồng thời toàn bộ quy trình đặt hàng.

Đánh giá độ rủi ro của lát cắt:

| Yếu tố | Rủi ro thấp hơn khi |
|---|---|
| Số caller | Ít caller hoặc caller có thể chuyển lần lượt |
| Hợp đồng | API nhỏ, đầu vào/đầu ra rõ |
| Dữ liệu | Có thể xác định một module sở hữu việc ghi |
| Tác động bên ngoài | Ít side effect hoặc có idempotency |
| Rollback | Có thể quay về implementation cũ mà không mất dữ liệu |
| Khả năng quan sát | Có metric để so sánh trước và sau |

Chọn lát cắt nhỏ không có nghĩa là chọn một lớp bất kỳ. Đơn vị chuyển đổi nên là một capability nghiệp vụ đủ hoàn chỉnh để có thể xác nhận hành vi từ đầu tới cuối.

## 4. Tạo ranh giới module mà chưa cần di chuyển tất cả caller

Khi đã chọn capability, tạo package gốc cho module và xác định API tối thiểu mà caller cần. Trong Spring Modulith, package gốc của application module là API package mặc định; package con chưa expose được giữ nội bộ khi module đóng.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryAvailability.java
│   ├── InventoryManagement.java
│   └── internal
│       ├── DefaultInventoryAvailability.java
│       └── InventoryRepository.java
└── legacy
    └── LegacyStockService.java
~~~

API của module:

~~~java
package com.example.shop.inventory;

public interface InventoryAvailability {

    int availableQuantity(String sku);
}
~~~

Implementation:

~~~java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
class DefaultInventoryAvailability implements InventoryAvailability {

    private final InventoryRepository repository;

    DefaultInventoryAvailability(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public int availableQuantity(String sku) {
        return repository.availableQuantity(sku);
    }
}
~~~

Implementation có thể nằm trong package internal. Caller chỉ biết interface InventoryAvailability. Repository và cách truy vấn dữ liệu vẫn thuộc quyền kiểm soát của module inventory.

Không cần di chuyển mọi class liên quan ngay trong bước đầu. Có thể đặt facade và interface tại ranh giới mới, sau đó chuyển từng implementation hoặc caller trong các bước tiếp theo.

## 5. Duy trì API cũ bằng facade tương thích

Một trong những cách giữ hệ thống chạy liên tục là giữ entry point cũ trong thời gian chuyển đổi. Facade cũ nhận request như trước nhưng ủy quyền sang API của module mới.

Ví dụ service cũ được nhiều caller sử dụng:

~~~java
package com.example.shop.legacy;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
public class LegacyStockService {

    private final InventoryAvailability inventory;

    public LegacyStockService(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    public int getAvailableQuantity(String sku) {
        return inventory.availableQuantity(sku);
    }
}
~~~

Các caller cũ tiếp tục gọi LegacyStockService. Caller mới có thể phụ thuộc trực tiếp vào InventoryAvailability. Nhờ đó, nhóm chuyển caller theo từng phần mà không phải đổi toàn bộ hệ thống trong cùng một release.

Facade tương thích cần giữ các đặc tính mà caller đang dựa vào:

- Method signature và kiểu dữ liệu trả về.
- Quy tắc validation và cách chuẩn hóa input.
- Exception hoặc error code có ý nghĩa với caller.
- Transaction semantics nếu caller phụ thuộc vào transaction hiện tại.
- Quy tắc bảo mật và authorization.
- Side effect và thứ tự xử lý đã được công bố.

Nếu API cũ trả về một kiểu legacy, facade có thể chuyển đổi giữa kiểu cũ và API mới. Hãy đặt mapping tại adapter/facade thay vì đưa kiểu legacy vào module mới nếu kiểu đó không thuộc hợp đồng nghiệp vụ ổn định.

## 6. Chuyển caller theo từng đợt nhỏ

Sau khi facade và module API hoạt động, chuyển caller từng nhóm:

~~~mermaid
flowchart TD
    A["Caller A"] --> L["Legacy facade"]
    B["Caller B"] --> L
    C["Caller C"] --> L
    L --> I["Inventory API"]
    D["Caller mới"] --> I
    A2["Caller A sau migration"] --> I
~~~

Một trình tự có thể áp dụng:

1. Giữ tất cả caller hiện tại đi qua facade cũ.
2. Chuyển một caller ít rủi ro sang API module mới.
3. Chạy test và quan sát kết quả caller đó.
4. Chuyển caller tiếp theo sau khi bước trước ổn định.
5. Theo dõi metric để xác nhận các luồng cũ và mới cho cùng kết quả.
6. Khi không còn caller sử dụng facade, đánh dấu deprecated và lên lịch loại bỏ.

Không nên xóa facade ngay khi caller đầu tiên đã chuyển. Cần xác nhận không còn caller ẩn như scheduled job, batch, integration adapter hoặc test fixture phụ thuộc API cũ.

Nếu cần dùng feature flag để chuyển traffic, flag nên chọn một implementation duy nhất cho mỗi request. Tránh gọi cả hai implementation rồi ghi cùng một nghiệp vụ hai lần chỉ để so sánh kết quả.

## 7. Chuyển quyền sở hữu dữ liệu theo nguyên tắc một writer

Legacy monolith thường cho phép nhiều service truy cập cùng bảng. Khi modular hóa, cần xác định module nào sở hữu dữ liệu và chịu trách nhiệm bảo vệ invariant.

Ví dụ trước refactor:

~~~text
OrderService       ─┐
ReportingService   ├──> INVENTORY_STOCK table
LegacyStockService ─┘
~~~

Sau khi xác định inventory là owner:

~~~text
Order module      ──> Inventory API ──> Inventory repository ──> STOCK
Reporting module  ──> Read API/projection được công bố
~~~

Các module khác không nên tiếp tục cập nhật trực tiếp bảng thuộc inventory. Nếu cần đọc, cung cấp API đọc hoặc projection phù hợp. Nếu cần thay đổi trạng thái, gọi capability của module sở hữu hoặc gửi command theo hợp đồng đã thống nhất.

### Tránh dual write

Không để implementation cũ và mới cùng ghi một nghiệp vụ vào hai nơi mà không có cơ chế đồng bộ rõ ràng. Dual write dễ tạo trạng thái lệch khi một lần ghi thành công còn lần ghi kia thất bại.

Nếu cần chuyển schema hoặc dữ liệu, sử dụng chiến lược expand-and-contract:

1. Mở rộng schema theo hướng tương thích ngược.
2. Triển khai code có thể đọc schema cũ và mới trong giai đoạn chuyển tiếp nếu cần.
3. Backfill dữ liệu bằng job có thể chạy lại an toàn.
4. Chuyển read path sang nguồn mới và so sánh kết quả.
5. Chuyển write ownership sang module mới tại một thời điểm kiểm soát được.
6. Theo dõi sai lệch và giữ đường rollback trong thời gian xác nhận.
7. Chỉ xóa cột, bảng hoặc code cũ sau khi không còn consumer cần chúng.

Ví dụ expand-and-contract:

~~~mermaid
flowchart LR
    A["Schema cũ"] --> B["Expand: thêm cấu trúc mới"]
    B --> C["Backfill và kiểm tra dữ liệu"]
    C --> D["Chuyển reader/writer"]
    D --> E["Theo dõi và xác nhận"]
    E --> F["Contract: bỏ cấu trúc cũ"]
~~~

Không xóa ngay schema cũ trong cùng release chuyển writer. Giữ khoảng tương thích để có thể khôi phục nếu phát hiện dữ liệu hoặc hành vi sai.

## 8. Giữ transaction boundary rõ ràng

Một lần modular hóa có thể vô tình thay đổi transaction semantics. Ví dụ trước đây OrderService và InventoryRepository cùng tham gia một transaction; sau refactor, một module gọi API khác hoặc xử lý event bất đồng bộ. Khi đó, hành vi rollback có thể thay đổi.

Trước khi chuyển, hãy trả lời:

- Các thao tác nào phải commit hoặc rollback cùng nhau?
- Có invariant nào cần được bảo vệ trong cùng transaction không?
- Caller có đang dựa vào dữ liệu vừa ghi trong transaction hiện tại không?
- Việc chuyển sang event có làm phản hồi thành eventual consistency không?
- Nếu bước sau thất bại, trạng thái nghiệp vụ được phục hồi hoặc bù trừ ra sao?

Nếu hai thao tác cần một kết quả đồng bộ để quyết định nghiệp vụ hiện tại, API trực tiếp trong cùng ứng dụng có thể phù hợp hơn. Không dùng event chỉ để làm mất một dependency nhìn thấy được trong sơ đồ.

Nếu side effect có thể diễn ra sau commit, application event và @ApplicationModuleListener có thể tách consumer khỏi publisher. Khi đó, consumer cần xử lý lặp an toàn và nhóm cần có cơ chế theo dõi publication nếu việc phục hồi là yêu cầu nghiệp vụ.

## 9. Dùng event cho phản ứng độc lập, không thay thế command

Event hữu ích khi một module muốn thông báo sự thật đã xảy ra và không cần biết các consumer cụ thể. Ví dụ, sau khi đơn được ghi nhận, notification có thể gửi email và analytics cập nhật số liệu.

~~~java
public record OrderSubmitted(
        UUID orderId,
        UUID customerId,
        Instant submittedAt) {
}
~~~

Publisher:

~~~java
events.publishEvent(new OrderSubmitted(
        order.getId(),
        order.getCustomerId(),
        Instant.now()));
~~~

Consumer:

~~~java
@Component
class OrderNotificationListener {

    @ApplicationModuleListener
    void on(OrderSubmitted event) {
        // Gửi thông báo sau khi transaction publisher commit.
    }
}
~~~

Không dùng event OrderSubmitted để yêu cầu inventory giữ hàng nếu publisher cần biết ngay giữ hàng có thành công để xác nhận đơn. Trong trường hợp đó, dùng API/command và nhận kết quả; sau khi giữ hàng thành công mới phát StockReserved.

Giữ event contract trong API package hoặc Named Interface được expose. Consumer không import event từ package internal của publisher.

## 10. Thêm kiểm tra kiến trúc sau mỗi bước

Khi module boundary đã được mô hình hóa, thêm architecture test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Chạy test này trong CI để phát hiện:

- Dependency cycle giữa các module.
- Consumer truy cập package internal chưa được expose.
- Dependency trực tiếp ngoài allowedDependencies.
- Named Interface hoặc module identifier tham chiếu không đúng.

Không đợi tới khi đã di chuyển toàn bộ hệ thống mới thêm kiểm tra. Khi một ranh giới đã được tạo, bảo vệ nó ngay để các thay đổi sau không làm ranh giới bị xói mòn.

Nếu legacy code chưa thể tuân thủ toàn bộ quy tắc, hãy chọn phạm vi migration có thể kiểm tra được và ghi rõ ngoại lệ có thời hạn. Tránh loại trừ cả package lớn khiến test xanh nhưng không bảo vệ được phần vừa modular hóa.

## 11. Kiểm thử theo từng lớp

Một bước chuyển đổi chỉ nên được xem là hoàn tất khi các loại kiểm tra phù hợp đã xác nhận hành vi.

| Lớp kiểm tra | Điều cần xác nhận |
|---|---|
| Unit test | Quy tắc nghiệp vụ trong module mới |
| Characterization test | Hành vi tương thích với implementation legacy |
| Contract/API test | Signature, response, exception và validation không bị thay đổi ngoài chủ đích |
| Repository/integration test | Query, transaction và dữ liệu được ghi đúng |
| Architecture test | Dependency, encapsulation và module boundary hợp lệ |
| Spring context test | Bean được đăng ký và inject sau khi chuyển package |
| End-to-end test | Luồng người dùng hoặc quy trình nghiệp vụ hoàn chỉnh |
| Migration/data test | Backfill, đối soát và schema transition chính xác |

Không cần chạy toàn bộ test suite nặng sau mỗi thay đổi nhỏ nếu pipeline đã có tầng kiểm tra phù hợp. Tuy nhiên, trước khi phát hành một lát cắt có ảnh hưởng dữ liệu hoặc contract, cần chạy đủ các test bảo vệ luồng liên quan.

## 12. Quan sát hệ thống trong thời gian chuyển đổi

Test xác nhận các trường hợp đã dự kiến. Production telemetry giúp phát hiện khác biệt trong tải thật và dữ liệu thật.

Nên theo dõi:

- Request count qua facade cũ và API module mới.
- Error rate theo caller và theo implementation.
- Latency p50/p95/p99 của capability được chuyển.
- Số lần retry hoặc lỗi listener nếu có event.
- Số lượng bản ghi được xử lý, giữ hàng hoặc cập nhật.
- Chênh lệch giữa kết quả đọc cũ và mới trong giai đoạn đối soát.
- Database lock, deadlock và thời gian transaction.
- Log có correlation ID để lần theo một nghiệp vụ qua nhiều module.

Đặt ngưỡng chấp nhận trước khi chuyển traffic. Ví dụ, không tăng tỷ lệ lỗi quá ngưỡng đã thống nhất và không làm latency vượt ngân sách của endpoint. Không chỉ quan sát tổng error rate; một caller ít lưu lượng có thể gặp lỗi toàn bộ nhưng bị che bởi traffic lớn từ caller khác.

## 13. Chuẩn bị rollback trước khi deploy

Rollback phải được thiết kế trước khi bắt đầu chuyển đổi, không phải nghĩ ra sau khi deployment thất bại.

Một bước có thể rollback khi:

- API cũ vẫn hoạt động hoặc có adapter tương thích.
- Schema mới vẫn tương thích với code cũ trong thời gian rollback.
- Chưa xóa dữ liệu mà implementation cũ cần.
- Không có hai writer cạnh tranh.
- Event consumer có idempotency và có thể xử lý publication còn tồn.
- Feature flag có thể chuyển traffic về đường đã biết hoạt động.

### Phân biệt rollback code và rollback dữ liệu

Code thường có thể quay về artifact trước đó. Dữ liệu đã ghi theo schema mới có thể không thể đảo ngược đơn giản. Vì vậy:

- Ưu tiên migration tương thích ngược.
- Không drop cột/bảng cũ ngay khi chuyển reader.
- Nếu có chuyển đổi dữ liệu không thể đảo ngược, chuẩn bị forward-fix hoặc compensating action thay vì giả định database rollback sẽ an toàn.
- Ghi lại version schema và version application trong deployment record.

Một feature flag chỉ giúp đổi đường thực thi. Nó không tự khôi phục dữ liệu đã bị ghi sai hoặc side effect đã gửi ra ngoài.

## 14. Lộ trình ví dụ cho module inventory

Giả sử inventory đang được xử lý bởi các service legacy và nhiều module truy cập trực tiếp bảng STOCK.

| Bước | Thay đổi | Điều kiện hoàn tất |
|---|---|---|
| 1. Baseline | Ghi nhận caller, query, invariant và metric | Có characterization test và số liệu trước chuyển |
| 2. API | Tạo InventoryAvailability tại package gốc | Hợp đồng nhỏ, có test |
| 3. Adapter | LegacyStockService delegate sang API mới | Caller cũ vẫn chạy |
| 4. Implementation | Đặt implementation và repository trong inventory.internal | Module mới sở hữu logic |
| 5. Caller migration | Chuyển từng caller sang InventoryAvailability | Test caller và metric đạt ngưỡng |
| 6. Data ownership | Ngừng ghi STOCK từ module ngoài inventory | Inventory là writer duy nhất |
| 7. Verification | Thêm ApplicationModules.verify() vào CI | Không còn violation trong phạm vi đã chuyển |
| 8. Cleanup | Loại bỏ facade cũ sau khi không còn caller | Search, telemetry và test xác nhận không còn sử dụng |

Mỗi bước có thể nằm trong một hoặc nhiều pull request, nhưng mỗi release cần giữ hệ thống ở trạng thái nhất quán. Nếu một bước cần nhiều lần deploy, hãy xác định trạng thái trung gian nào vẫn tương thích với cả phiên bản trước và sau.

## 15. Những cách chuyển đổi dễ làm hệ thống gián đoạn

| Cách làm | Rủi ro | Cách thay thế |
|---|---|---|
| Di chuyển toàn bộ package và đổi API trong một release | Khó khoanh vùng lỗi, caller cũ bị gãy | Tạo API và facade tương thích trước |
| Xóa facade ngay sau khi chuyển một caller | Caller ẩn hoặc batch job có thể vẫn dùng API cũ | Chuyển caller lần lượt, quan sát rồi mới xóa |
| Cho cả implementation cũ và mới cùng ghi | Dữ liệu lệch hoặc duplicate side effect | Chọn một writer, chuyển ownership tại thời điểm kiểm soát |
| Drop schema cũ ngay sau backfill | Rollback code có thể không còn tương thích | Dùng expand-and-contract và giữ thời gian tương thích |
| Dùng event cho command cần kết quả ngay | Luồng nghiệp vụ chuyển thành eventual consistency ngoài dự kiến | Gọi API/command và nhận kết quả |
| Bỏ qua test characterization | Refactor có thể làm thay đổi hành vi cũ mà không nhận ra | Ghi nhận behavior trước khi đổi cấu trúc |
| Chỉ kiểm tra startup | Không phát hiện sai lệch nghiệp vụ hoặc dữ liệu | Kết hợp architecture, integration và end-to-end test |
| Nới toàn bộ module thành OPEN để tránh lỗi | Internal package bị expose rộng | Công bố API package hoặc Named Interface có chọn lọc |
| Rollback code nhưng không xét dữ liệu | Code cũ không đọc được schema/dữ liệu mới | Thiết kế tương thích ngược và kế hoạch data recovery |

## 16. Khi nào một bước modular hóa được xem là hoàn tất?

Một bước không hoàn tất chỉ vì code đã được chuyển sang package mới. Hãy xác định điều kiện chấp nhận cụ thể:

- Hành vi nghiệp vụ vẫn đúng với contract đã thống nhất.
- Caller cũ được hỗ trợ hoặc đã được chuyển hết có bằng chứng.
- Module mới sở hữu logic và dữ liệu theo phạm vi đã chọn.
- Không còn dependency trực tiếp ngoài ý muốn trong lát cắt đã chuyển.
- Architecture test bảo vệ ranh giới mới.
- Context và integration test xác nhận bean, transaction và persistence hoạt động.
- Metric không vượt ngưỡng lỗi/latency đã thống nhất.
- Có thể rollback code/config mà không làm mất dữ liệu hoặc gây duplicate side effect.
- Tài liệu module và sơ đồ dependency phản ánh cấu trúc hiện tại.

Nếu còn caller dùng facade cũ, bước tạo module vẫn có thể hoàn tất; nhưng việc loại bỏ facade là một bước riêng với điều kiện hoàn tất riêng.

## 17. Quy trình làm việc lặp lại cho từng lát cắt

Có thể dùng vòng lặp sau cho mỗi capability:

1. **Khảo sát:** xác định owner, caller, dữ liệu, contract và side effect.
2. **Đo baseline:** bổ sung test và metric cho hành vi hiện tại.
3. **Tạo boundary:** đặt API ở package gốc hoặc Named Interface.
4. **Adapter:** giữ entry point cũ và delegate sang module mới.
5. **Chuyển implementation:** di chuyển logic, repository và policy theo từng phần.
6. **Chuyển caller:** cập nhật từng consumer và xác nhận bằng test.
7. **Chuyển data ownership:** bảo đảm một writer và schema tương thích.
8. **Bảo vệ dependency:** thêm allowedDependencies và ApplicationModules.verify().
9. **Triển khai/quan sát:** rollout từng bước, theo dõi metric và log.
10. **Dọn legacy:** chỉ xóa facade, code và schema cũ khi không còn caller và rollback window đã kết thúc.

Lặp lại vòng này cho module tiếp theo. Sau mỗi lát cắt, cập nhật dependency map để nhóm nhìn thấy coupling còn lại và chọn bước kế tiếp dựa trên dữ liệu thực tế.

## 18. Checklist giữ hệ thống hoạt động trong quá trình modular hóa

- [ ] Có baseline về hành vi, caller, dữ liệu và metric của capability được chọn.
- [ ] Lát cắt có ranh giới nghiệp vụ rõ và đủ nhỏ để review.
- [ ] API module mới thể hiện capability thay vì lộ implementation.
- [ ] Có facade/adapter giữ contract cũ khi caller chưa chuyển hết.
- [ ] Caller được chuyển theo từng nhóm và có kiểm chứng sau mỗi lần chuyển.
- [ ] Một module chịu trách nhiệm ghi dữ liệu cho nghiệp vụ tại một thời điểm.
- [ ] Không có dual write không được kiểm soát.
- [ ] Schema migration theo hướng tương thích ngược.
- [ ] Transaction boundary và consistency semantics được xác định rõ.
- [ ] Event chỉ dùng cho sự thật đã xảy ra và consumer độc lập.
- [ ] Architecture test bảo vệ dependency và encapsulation.
- [ ] Integration/context test xác nhận dữ liệu và bean runtime.
- [ ] Metric, log và correlation ID đủ để phát hiện lỗi.
- [ ] Có rollback plan cho code, cấu hình và dữ liệu.
- [ ] Chỉ loại bỏ facade/schema cũ khi đã có bằng chứng không còn sử dụng.

## 19. Kết luận

Giữ hệ thống chạy được trong từng bước là điều kiện cốt lõi khi modular hóa legacy. Hãy bắt đầu bằng baseline có thể quan sát, chọn một capability nghiệp vụ, tạo API module rõ ràng và giữ facade tương thích để caller cũ tiếp tục hoạt động. Sau đó chuyển implementation, caller và quyền sở hữu dữ liệu theo từng bước có thể kiểm thử và triển khai độc lập.

Không để hai module cùng ghi một nghiệp vụ, không thay đổi transaction semantics ngoài chủ đích và không dùng event để thay thế command cần kết quả ngay. Mỗi bước cần architecture test, integration test, metric và rollback plan. Khi một ranh giới đã ổn định, dùng ApplicationModules.verify() để bảo vệ nó trong CI; chỉ xóa adapter và schema cũ sau khi đã xác nhận không còn caller. Cách chuyển đổi này cho phép ứng dụng tiếp tục phục vụ trong khi cấu trúc bên trong dần trở thành modular monolith có ranh giới rõ ràng.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [Martin Fowler — Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)
