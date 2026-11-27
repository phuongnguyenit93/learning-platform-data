# Kiểm tra ảnh hưởng tới docs, tests và events

## Mục tiêu đánh giá

Trong một ứng dụng modular monolith, thay đổi ở một module thường ảnh hưởng đến nhiều phần hơn đoạn mã vừa sửa. Một phương thức công khai có thể được module khác gọi; một sự kiện có thể có nhiều listener; một quy tắc phụ thuộc có thể được ghi trong tài liệu kiến trúc và được bảo vệ bằng bài kiểm thử. Nếu chỉ đọc phần diff của mã nguồn, người review dễ bỏ sót những hợp đồng này.

Spring Modulith giúp mô hình hóa module, Named Interface, phụ thuộc và tương tác qua sự kiện trong ứng dụng Spring Boot. Khi đánh giá một thay đổi thiết kế, cần lần theo ảnh hưởng của nó đến ba nhóm artefact: tài liệu (docs), kiểm thử (tests) và sự kiện (events). Ba nhóm này cho biết thiết kế mới có được mô tả đúng, được kiểm tra đúng và vẫn giữ ngữ nghĩa giao tiếp giữa các module hay không.

Sau bài học, bạn có thể:

- Xác định hợp đồng kiến trúc nào bị ảnh hưởng bởi một thay đổi module.
- Đánh giá tài liệu module, sơ đồ phụ thuộc, Named Interface và tài liệu sự kiện.
- Chọn các bài kiểm thử cần cập nhật để bảo vệ cấu trúc và hành vi mới.
- Kiểm tra quyền sở hữu, payload, listener và ngữ nghĩa xử lý của sự kiện.
- Viết nhận xét review có căn cứ và đưa ra quyết định chấp nhận thiết kế.

## 1. Bắt đầu từ thay đổi thiết kế và hợp đồng bị tác động

Một design review nên bắt đầu bằng việc mô tả rõ trạng thái hiện tại, thay đổi đề xuất và lý do nghiệp vụ. Sau đó xác định những hợp đồng mà các module khác đang sử dụng.

Trong Spring Modulith, các hợp đồng thường nằm ở những nơi sau:

| Hợp đồng | Câu hỏi cần trả lời khi review |
|---|---|
| Ranh giới module | Package nào thuộc module nào? Có module nào mới được tạo, gộp hoặc tách không? |
| API công khai | Kiểu và phương thức nào được module khác sử dụng? Chữ ký hoặc ý nghĩa của chúng có đổi không? |
| Named Interface | Package con nào được công khai? Tên interface hoặc phạm vi truy cập có thay đổi không? |
| Quy tắc phụ thuộc | Hướng phụ thuộc có đổi không? Có phát sinh chu trình hoặc phụ thuộc ngoài `allowedDependencies` không? |
| Sự kiện | Module nào phát sự kiện, module nào xử lý, và ý nghĩa hoặc payload có thay đổi không? |
| Tài liệu và kiểm thử | Sơ đồ, hướng dẫn, ví dụ và test nào đang mô tả hợp đồng cũ? |

Đừng chỉ hỏi “file nào đã đổi?”. Hãy hỏi “module nào đang dựa vào hợp đồng này và điều gì sẽ xảy ra với chúng sau thay đổi?”. Một thay đổi có thể không sửa trực tiếp một listener nhưng vẫn làm listener đó không còn nhận được payload hoặc không còn chạy đúng thời điểm.

## 2. Tình huống xuyên suốt: chuyển lời gọi trực tiếp thành sự kiện

Giả sử module `orders` hiện gọi trực tiếp API của `inventory` khi đơn hàng được tạo:

```text
orders ───────► inventory
```

Mã nguồn của `orders` có thể phụ thuộc vào một API công khai như `InventoryReservation`. Nhóm đề xuất chuyển sang mô hình sự kiện: `orders` công bố sự kiện `OrderPlaced`, còn `inventory` lắng nghe sự kiện để giữ chỗ tồn kho.

Sự kiện thuộc module phát sinh sự kiện nghiệp vụ:

```java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
```

Module `inventory` nhận sự kiện:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Tìm các mặt hàng của đơn và thực hiện giữ chỗ tồn kho.
    }
}
```

Đây là ví dụ rút gọn về hợp đồng sự kiện; xử lý giữ chỗ thực tế cần dữ liệu đơn hàng phù hợp và quy tắc xử lý lỗi riêng.

Thay đổi này ảnh hưởng đến cả ba hướng đánh giá:

- **Docs:** sơ đồ cần mô tả luồng sự kiện từ `orders` đến `inventory`, đồng thời thể hiện đúng quan hệ phụ thuộc mã nguồn.
- **Tests:** cần kiểm tra cấu trúc module, việc phát sự kiện, listener và kết quả giữ chỗ.
- **Events:** cần xem xét tên sự kiện, payload, thời điểm phát, giao dịch, xử lý lặp và lỗi listener.

Một điểm dễ nhầm là hướng luồng sự kiện lúc chạy khác với hướng phụ thuộc mã nguồn. `orders` phát `OrderPlaced`; `inventory` import kiểu sự kiện đó để xử lý. Vì vậy, luồng sự kiện chạy từ `orders` sang `inventory`, trong khi phụ thuộc biên dịch được hình thành từ `inventory` đến `orders`. Khi review, hãy ghi rõ cả hai quan hệ này thay vì dùng một mũi tên chung cho cả hai.

## 3. Đánh giá ảnh hưởng tới tài liệu (docs)

Tài liệu phải phản ánh thiết kế đang tồn tại. Khi module, API hoặc sự kiện thay đổi, hãy tìm những tài liệu có thể trở nên sai hoặc thiếu.

### 3.1. Tài liệu module và sơ đồ kiến trúc

Kiểm tra các nội dung sau:

- Danh sách module và trách nhiệm nghiệp vụ của từng module.
- Package gốc, package nội bộ và các Named Interface được công khai.
- Sơ đồ phụ thuộc giữa các module.
- Sơ đồ luồng sự kiện, gồm module phát và các module nhận.
- Quy tắc phụ thuộc được phép và các ngoại lệ đã được giải thích.

Nếu dự án sử dụng khả năng tạo tài liệu của Spring Modulith, hãy xác định artefact nào được sinh tự động và chạy lại đúng bước tạo tài liệu của dự án. Đọc kết quả sau khi sinh để xác nhận sơ đồ phản ánh đúng package và quan hệ hiện tại. Tài liệu được sinh tự động vẫn cần được kiểm tra vì nó có thể cho thấy một phụ thuộc mới mà nhóm chưa chủ ý tạo ra.

Đối với ví dụ `OrderPlaced`, không nên chỉ đổi mũi tên `orders → inventory` thành `inventory → orders` rồi dừng lại. Sơ đồ cần phân biệt quan hệ phụ thuộc mã nguồn với luồng sự kiện lúc chạy. Nếu tài liệu không phân biệt hai khái niệm này, người đọc có thể hiểu sai quyền sở hữu và trình tự tương tác.

### 3.2. Tài liệu API và Named Interface

Khi thay đổi API công khai, kiểm tra:

- Tên kiểu, chữ ký phương thức, tham số, kiểu trả về và ngoại lệ có thể phát sinh.
- Package chứa API có còn được công khai theo thiết kế không.
- Named Interface có giữ nguyên tên và phạm vi không.
- Ví dụ mã nguồn, hướng dẫn tích hợp và tài liệu onboarding có còn biên dịch hoặc còn đúng ngữ nghĩa không.
- Có tài liệu nào đang hướng dẫn module khác gọi trực tiếp implementation nội bộ không.

Nếu một API đồng bộ được thay bằng sự kiện, tài liệu phải giải thích sự khác nhau về cách sử dụng. Một lời gọi đồng bộ có thể trả kết quả ngay cho bên gọi; sự kiện thường chỉ xác nhận sự kiện đã được công bố, còn công việc của listener có thể hoàn tất sau đó. Không giữ lại câu mô tả cũ khiến người dùng API kỳ vọng tồn kho đã được giữ chỗ ngay khi đơn hàng được tạo.

### 3.3. Tài liệu sự kiện và vận hành

Với mỗi sự kiện liên module, tài liệu nên cho biết:

| Nội dung | Điều cần mô tả |
|---|---|
| Ý nghĩa nghiệp vụ | Sự kiện biểu thị sự thật nào đã xảy ra? |
| Chủ sở hữu | Module nào định nghĩa và công bố sự kiện? |
| Payload | Các trường có ý nghĩa gì, có bắt buộc không và được tạo ở thời điểm nào? |
| Người nhận | Module hoặc listener nào xử lý sự kiện? |
| Thời điểm xử lý | Xử lý ngay, sau commit hay bất đồng bộ theo cấu hình nào? |
| Lỗi và phục hồi | Khi listener thất bại, nhóm quan sát, thử lại và xử lý tồn đọng ra sao? |
| Tương thích | Thay đổi payload ảnh hưởng thế nào tới listener hoặc hệ thống tích hợp cũ? |

Tài liệu vận hành cần chỉ ra nơi xem log, metric hoặc trạng thái publication mà ứng dụng đang sử dụng. Nếu hệ thống dựa vào cơ chế theo dõi event publication của Spring Modulith, hãy mô tả cách nhóm kiểm tra publication chưa hoàn tất và quy trình xử lý lỗi tương ứng với cấu hình thực tế.

## 4. Đánh giá ảnh hưởng tới kiểm thử (tests)

Một thay đổi thiết kế thường cần nhiều lớp kiểm thử. Không nên kỳ vọng một bài test duy nhất chứng minh được cả cấu trúc module, hợp đồng sự kiện và hành vi nghiệp vụ.

### 4.1. Kiểm thử cấu trúc module

Giữ một bài kiểm thử kiến trúc gọi `ApplicationModules.verify()` để phát hiện các vi phạm về phụ thuộc, truy cập package nội bộ và chu trình module:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Sau khi chuyển sang sự kiện, chạy lại bài test này và đọc đồ thị phụ thuộc mới. Nếu listener trong `inventory` import `OrderPlaced` từ `orders`, quan hệ phụ thuộc mã nguồn phải được hiểu và chấp nhận có chủ đích. Nếu thay đổi tạo thêm một cạnh làm xuất hiện chu trình, cần xem lại quyền sở hữu sự kiện hoặc hướng giao tiếp.

Nếu dự án khai báo `allowedDependencies`, cập nhật hợp đồng chỉ khi quan hệ mới thực sự được thiết kế và chấp thuận. Không thêm module vào danh sách một cách máy móc chỉ để làm test thành công.

### 4.2. Kiểm thử trong phạm vi module

Khi thay đổi ảnh hưởng đến hành vi bên trong một module, bổ sung hoặc cập nhật test cho chính module đó. `@ApplicationModuleTest` của Spring Modulith hỗ trợ tạo ngữ cảnh kiểm thử theo phạm vi module và các chế độ bootstrap được cấu hình.

Với `inventory`, các trường hợp cần kiểm tra có thể gồm:

- Listener nhận đúng sự kiện `OrderPlaced`.
- Sự kiện có mã đơn hợp lệ dẫn đến yêu cầu giữ chỗ tương ứng.
- Sự kiện thiếu dữ liệu bắt buộc được xử lý theo quy tắc đã thống nhất.
- Lỗi khi giữ chỗ được ghi nhận và phục hồi theo chính sách của module.
- Listener không vô tình gọi ngược vào implementation nội bộ của `orders`.

Test của module nên tập trung vào trách nhiệm mà module sở hữu. Nếu một thay đổi làm đổi hợp đồng công khai, cập nhật thêm test ở nơi tiêu thụ hợp đồng để xác nhận hai phía vẫn tương thích.

### 4.3. Kiểm thử tương tác sự kiện

Với tương tác liên module, kiểm tra cả việc công bố sự kiện và kết quả xử lý. Spring Modulith cung cấp `Scenario` trong test support để mô tả luồng sự kiện và chờ sự kiện tiếp theo.

Ví dụ minh họa một test chờ `StockReserved` sau khi công bố `OrderPlaced`:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

import java.time.Instant;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ApplicationModuleTest
class InventoryEventTests {

    @Autowired
    Scenario scenario;

    @Test
    void reservesStockForPlacedOrder() {
        var orderId = UUID.randomUUID();

        scenario.publish(new OrderPlaced(orderId, Instant.now()))
                .andWaitForEventOfType(StockReserved.class)
                .toArriveAndVerify(event ->
                        assertEquals(orderId, event.orderId())
                );
    }
}
```

Đoạn mã giả định module `inventory` phát `StockReserved` sau khi giữ chỗ thành công và các kiểu sự kiện được khai báo phù hợp trong dự án. Bổ sung import, fixture và assertion theo cấu trúc test thực tế.

Không chỉ kiểm tra rằng listener được gọi. Hãy xác nhận kết quả nghiệp vụ, ví dụ mã đơn, số lượng đã giữ chỗ và trạng thái được ghi nhận. Với listener chạy sau commit hoặc bất đồng bộ, test phải chờ kết quả theo cơ chế hỗ trợ của Spring Modulith thay vì giả định listener hoàn tất ngay trong câu lệnh publish.

### 4.4. Kiểm thử lỗi, giao dịch và xử lý lặp

Review sự kiện cần đặt ra các trường hợp không xảy ra trong luồng thành công:

- Giao dịch phát sự kiện rollback: listener có được chạy theo ngữ nghĩa đã chọn không?
- Listener thất bại: publication có được ghi nhận hoặc phục hồi theo cấu hình không?
- Một sự kiện được xử lý lại: thao tác có an toàn khi lặp không?
- Hai sự kiện đến gần nhau hoặc sai thứ tự: trạng thái nghiệp vụ có còn hợp lệ không?
- Payload thiếu trường hoặc mang giá trị không còn được hỗ trợ: listener phản ứng thế nào?

Nếu dùng `@ApplicationModuleListener`, hãy xác nhận nhóm hiểu và kiểm thử đúng ngữ nghĩa listener theo cấu hình của Spring Modulith, đặc biệt là việc xử lý bất đồng bộ và gắn với giao dịch. Không mặc định rằng publish event đồng nghĩa mọi listener đã hoàn thành.

## 5. Đánh giá ảnh hưởng tới sự kiện (events)

Sự kiện là hợp đồng giữa module phát và module nhận. Một thay đổi ở tên lớp hoặc package có thể ảnh hưởng đến biên dịch; một thay đổi ý nghĩa hoặc payload có thể làm listener xử lý sai dù mã nguồn vẫn biên dịch.

### 5.1. Xác định chủ sở hữu và ý nghĩa sự kiện

Tên sự kiện nên diễn tả một sự thật nghiệp vụ đã xảy ra, thường dùng dạng quá khứ như `OrderPlaced`, `PaymentAuthorized` hoặc `StockReserved`. Trước khi đổi sự kiện, hãy xác định:

- Sự kiện phản ánh sự thật nào và module nào có thẩm quyền xác nhận sự thật đó?
- Nó được phát sau khi điều kiện nghiệp vụ nào đã được thỏa mãn?
- Listener cần biết sự thật đó hay đang bị yêu cầu thực hiện một lệnh?
- Có đang dùng một sự kiện để truyền lệnh điều khiển thay cho API phù hợp không?

Ví dụ, `OrderPlaced` nên có nghĩa đơn hàng đã được tạo theo quy tắc của module `orders`. Nếu đơn hàng chỉ mới được yêu cầu tạo và còn có thể bị từ chối, một sự kiện mang tên `OrderPlaced` sẽ mô tả sai trạng thái. Cần chọn tên và thời điểm phát phản ánh đúng sự thật nghiệp vụ.

### 5.2. Kiểm tra payload và khả năng tương thích

Payload nên chứa dữ liệu cần thiết cho listener, có kiểu rõ ràng và không làm lộ implementation nội bộ. Tránh đưa trực tiếp JPA entity, đối tượng mutable hoặc toàn bộ aggregate vào sự kiện chỉ vì listener muốn truy cập một vài trường.

Khi sửa payload, kiểm tra:

- Thêm trường mới có giá trị mặc định hoặc cách xử lý khi thiếu không?
- Đổi tên hoặc xóa trường có làm listener cũ không đọc được không?
- Đổi kiểu dữ liệu có làm thay đổi ý nghĩa hoặc cách serialize không?
- Đổi package hoặc tên lớp có ảnh hưởng đến nơi lưu trữ publication hay tích hợp bên ngoài không?
- Có cần chiến lược phiên bản hóa hoặc chuyển đổi payload không?

Trong ứng dụng chỉ xử lý event nội bộ, thay đổi kiểu sự kiện vẫn ảnh hưởng đến các module tiêu thụ ở thời điểm biên dịch. Nếu sự kiện được lưu trữ, externalize hoặc gửi tới hệ thống khác, cần xem thêm khả năng đọc lại dữ liệu cũ và tương thích schema ở thời điểm chạy.

### 5.3. Kiểm tra thời điểm phát và giao dịch

Một sự kiện có thể được phát trước hoặc sau khi dữ liệu nghiệp vụ được commit. Sự khác biệt này quyết định listener có nhìn thấy trạng thái đã lưu hay không và có thể gây ra tác dụng phụ khi giao dịch gốc rollback.

Khi review, hãy xác nhận:

- Sự kiện được phát sau khi điều kiện nghiệp vụ đã được xác nhận.
- Listener cần chạy trong giao dịch hiện tại hay sau khi giao dịch commit.
- Listener có chạy bất đồng bộ không và bên phát có cần kết quả ngay không.
- Lỗi listener có ảnh hưởng đến giao dịch phát sự kiện hay được xử lý độc lập.
- Có yêu cầu đảm bảo thứ tự xử lý giữa các sự kiện không.

Nếu chuyển từ lời gọi trực tiếp sang listener sau commit, hành vi hệ thống có thể thay đổi từ đồng bộ sang eventual consistency. UI hoặc API của `orders` không nên trả về thông điệp “đã giữ chỗ tồn kho” nếu chỉ mới công bố `OrderPlaced`. Có thể cần trạng thái trung gian như `PENDING_RESERVATION`, sau đó cập nhật khi nhận kết quả từ module `inventory`.

### 5.4. Kiểm tra listener, trùng lặp và phục hồi

Lập danh sách tất cả listener của sự kiện bị tác động. Với từng listener, kiểm tra:

- Listener có còn nhận đúng kiểu sự kiện sau khi đổi package hoặc payload không?
- Listener có thực hiện đúng trách nhiệm của module sở hữu nó không?
- Xử lý lại cùng một sự kiện có gây giữ chỗ hai lần hoặc gửi thông báo trùng không?
- Lỗi tạm thời có thể phục hồi mà không làm mất trạng thái nghiệp vụ không?
- Có thể quan sát listener bị lỗi hoặc publication chưa hoàn tất không?

Nếu dùng cơ chế event publication registry, hiểu rõ trạng thái publication và cách ứng dụng đánh dấu hoàn tất. Không coi việc ghi nhận sự kiện đã được phát là bằng chứng mọi listener đã xử lý thành công.

## 6. So sánh trước và sau thay đổi

Bảng dưới đây minh họa cách đánh giá đề xuất chuyển từ lời gọi trực tiếp sang sự kiện:

| Hạng mục | Trước thay đổi | Sau thay đổi | Bằng chứng cần review |
|---|---|---|---|
| Tương tác | `orders` gọi API `inventory` | `orders` phát `OrderPlaced`, `inventory` xử lý | Sơ đồ luồng và mô tả hợp đồng |
| Phụ thuộc mã nguồn | `orders` phụ thuộc `inventory` | `inventory` phụ thuộc kiểu sự kiện thuộc `orders` | Kết quả `ApplicationModules.verify()` và sơ đồ module |
| Kết quả trả về | Có thể nhận kết quả đồng bộ từ API | Listener có thể hoàn tất sau đó | API response, trạng thái trung gian và tài liệu hành vi |
| Kiểm thử | Test lời gọi và kết quả giữ chỗ | Test publish, listener, kết quả và lỗi | Unit test, module test, event scenario |
| Vận hành | Theo dõi lỗi lời gọi đồng bộ | Theo dõi listener, publication và xử lý lại | Log, metric, runbook và quy trình phục hồi |

Nếu thiết kế sau thay đổi không có câu trả lời cho một hàng trong bảng, review chưa có đủ bằng chứng để kết luận.

## 7. Quy trình thực hiện một design review

Có thể áp dụng quy trình sau cho pull request thay đổi ranh giới module, API hoặc sự kiện:

1. **Đọc mục tiêu thay đổi:** ghi lại vấn đề nghiệp vụ, hành vi hiện tại và hành vi mong đợi.
2. **Lập bản đồ hợp đồng:** xác định module sở hữu API, Named Interface, quy tắc phụ thuộc và sự kiện liên quan.
3. **Truy vết bên sử dụng:** tìm các module gọi API, import kiểu sự kiện, triển khai listener hoặc tham chiếu tài liệu cũ.
4. **Đánh giá docs:** cập nhật mô tả module, sơ đồ, ví dụ, hợp đồng sự kiện và hướng dẫn vận hành.
5. **Đánh giá tests:** cập nhật architecture test, module test, test của API và event scenario cho các luồng thành công lẫn lỗi.
6. **Đánh giá semantics của event:** kiểm tra quyền sở hữu, payload, thời điểm phát, giao dịch, bất đồng bộ, xử lý lặp và phục hồi.
7. **Đọc bằng chứng:** chạy các test phù hợp trong quy trình dự án, xem tài liệu được tạo và kiểm tra các thay đổi trong sơ đồ phụ thuộc.
8. **Ghi quyết định:** nêu rõ điều kiện chấp nhận, rủi ro còn lại, người chịu trách nhiệm và tài liệu hoặc test còn thiếu.

Review nên phân biệt lỗi chặn phát hành với cải tiến có thể lên kế hoạch sau. Ví dụ, phụ thuộc vòng mới hoặc payload làm listener không thể xử lý là vấn đề cần giải quyết trước khi chấp nhận. Một sơ đồ phụ chưa được cập nhật cũng cần sửa để tránh tài liệu sai, nhưng cách xử lý ưu tiên có thể khác tùy quy trình nhóm.

## 8. Mẫu bảng ghi nhận kết quả review

Sử dụng bảng này trong mô tả pull request hoặc biên bản design review:

| Nhóm | Nội dung thay đổi | Bên bị ảnh hưởng | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| Docs | Sơ đồ module, API, event catalog, runbook | Người phát triển và vận hành | Tài liệu cập nhật hoặc bản sinh mới | Chưa kiểm tra / Đạt / Cần sửa |
| Tests | Architecture test, module test, event scenario | Module phát và nhận | Kết quả test và báo cáo lỗi | Chưa kiểm tra / Đạt / Cần sửa |
| Events | Tên, payload, owner, listener, transaction | Tất cả consumer | Danh sách listener, test tương thích và xử lý lỗi | Chưa kiểm tra / Đạt / Cần sửa |

Một nhận xét review tốt nêu rõ bằng chứng và hệ quả. Ví dụ:

> `inventory` hiện import `OrderPlaced` từ `orders`, nên quan hệ phụ thuộc mã nguồn đã đổi hướng dù luồng sự kiện chạy từ `orders` sang `inventory`. Sơ đồ hiện chỉ thể hiện luồng runtime. Hãy cập nhật sơ đồ để phân biệt hai quan hệ và giữ architecture test xác nhận đồ thị phụ thuộc mới.

Hoặc:

> Listener được chạy sau khi giao dịch tạo đơn commit. API hiện tại vẫn trả trạng thái “đã giữ chỗ” ngay sau khi publish event, trong khi chưa có bằng chứng listener đã hoàn tất. Cần thống nhất trạng thái phản hồi và bổ sung test cho trường hợp listener thất bại trước khi chấp nhận thay đổi.

## 9. Checklist trước khi chấp nhận thiết kế

### Docs

- [ ] Tài liệu mô tả đúng trách nhiệm và ranh giới của từng module.
- [ ] Sơ đồ phụ thuộc phân biệt quan hệ mã nguồn với luồng sự kiện lúc chạy.
- [ ] API công khai và Named Interface được mô tả đúng.
- [ ] Event catalog nêu rõ ý nghĩa, owner, payload và listener.
- [ ] Ví dụ, hướng dẫn và runbook không còn mô tả hành vi cũ.

### Tests

- [ ] `ApplicationModules.verify()` xác nhận cấu trúc module hợp lệ.
- [ ] Test module bao phủ hành vi thay đổi ở module sở hữu.
- [ ] Test API hoặc consumer kiểm tra hợp đồng sau thay đổi.
- [ ] Event scenario xác nhận listener và kết quả nghiệp vụ.
- [ ] Có kiểm thử cho lỗi, rollback, xử lý lặp hoặc phục hồi khi các trường hợp này liên quan.

### Events

- [ ] Sự kiện biểu thị đúng sự thật nghiệp vụ và có owner rõ ràng.
- [ ] Payload đủ dùng, ổn định và không làm lộ implementation nội bộ.
- [ ] Thời điểm phát và ngữ nghĩa giao dịch được xác nhận.
- [ ] Listener, tính bất đồng bộ và thứ tự xử lý phù hợp với yêu cầu.
- [ ] Trùng lặp, lỗi và publication chưa hoàn tất có cách xử lý rõ ràng.
- [ ] Thay đổi payload tương thích với consumer và dữ liệu đã lưu nếu có.

Chỉ đánh dấu một mục là đạt khi có bằng chứng cụ thể, chẳng hạn diff tài liệu, kết quả test hoặc danh sách listener đã được kiểm tra. Một câu “đã xem qua” không đủ để chứng minh hợp đồng vẫn đúng.

## 10. Bài tập thực hành

Giả sử nhóm đang xem xét chuyển thao tác giữ chỗ tồn kho từ lời gọi đồng bộ trong `orders` sang sự kiện `OrderPlaced`.

**Nhiệm vụ A — Truy vết thiết kế**

1. Ghi lại API hiện tại mà `orders` gọi trong `inventory`.
2. Xác định package, Named Interface và quy tắc phụ thuộc liên quan.
3. Vẽ riêng đồ thị phụ thuộc mã nguồn và luồng tương tác lúc chạy của thiết kế đề xuất.
4. Liệt kê các module, listener và tài liệu có thể bị ảnh hưởng.

**Nhiệm vụ B — Review docs**

1. Viết lại mô tả tương tác giữa `orders` và `inventory` theo thiết kế sự kiện.
2. Cập nhật sơ đồ để thể hiện rõ hai hướng quan hệ.
3. Bổ sung định nghĩa `OrderPlaced`, owner, payload và listener vào tài liệu sự kiện.
4. Viết rõ khi nào API tạo đơn được phép báo kết quả giữ chỗ thành công.

**Nhiệm vụ C — Review tests**

1. Chạy architecture test và ghi nhận đồ thị phụ thuộc sau thay đổi.
2. Viết test cho listener giữ chỗ khi nhận `OrderPlaced`.
3. Viết event scenario xác nhận kết quả `StockReserved`.
4. Kiểm tra tình huống listener thất bại và sự kiện được xử lý lại.
5. Xác nhận API tạo đơn không báo hoàn tất giữ chỗ trước khi có kết quả tương ứng.

**Nhiệm vụ D — Review event contract**

1. Xác định module sở hữu `OrderPlaced` và giải thích vì sao.
2. Đánh giá các trường của payload và dữ liệu listener thực sự cần.
3. Xác định thời điểm phát sự kiện so với commit giao dịch.
4. Mô tả cách xử lý lỗi, trùng lặp và publication chưa hoàn tất.
5. Viết quyết định review: chấp nhận, yêu cầu sửa hoặc cần thêm thông tin; nêu bằng chứng cho quyết định.

## 11. Tiêu chí hoàn thành

- Người review xác định được tất cả hợp đồng module bị thay đổi và các bên tiêu thụ liên quan.
- Tài liệu phản ánh đúng ranh giới, phụ thuộc mã nguồn và luồng sự kiện.
- Architecture test và các test hành vi liên quan bảo vệ được thiết kế mới.
- Event contract có owner, payload, thời điểm phát và quy tắc xử lý lỗi rõ ràng.
- Các thay đổi về đồng bộ, bất đồng bộ và eventual consistency được phản ánh trong API và tài liệu.
- Quyết định review nêu rõ bằng chứng, rủi ro còn lại và điều kiện cần hoàn tất.

Một design review hoàn chỉnh giúp nhóm nhìn thấy tác động của thay đổi trên toàn bộ hợp đồng module. Tài liệu cho biết hệ thống được thiết kế ra sao, test bảo vệ những quy tắc nào, còn sự kiện xác định cách các module phối hợp khi nghiệp vụ diễn ra. Khi cả ba cùng phản ánh một thiết kế, modular monolith có thể tiếp tục phát triển mà không làm mất đi ranh giới và ý nghĩa giao tiếp giữa các module.
