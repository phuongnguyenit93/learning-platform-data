# Chọn module test và phạm vi context

Một bài kiểm thử mô-đun cần xác định rõ phần nào của ứng dụng được khởi tạo trong Spring `ApplicationContext`. Nếu chỉ kiểm thử logic của một mô-đun, việc nạp toàn bộ ứng dụng có thể làm test chậm và khiến lỗi từ mô-đun khác ảnh hưởng đến kết quả. Ngược lại, nếu use case cần phối hợp nhiều mô-đun thật, chỉ nạp một mô-đun rồi mock mọi collaborator có thể bỏ sót lỗi tích hợp.

Spring Modulith cung cấp `@ApplicationModuleTest` để tạo context tập trung vào một application module. Thuộc tính `mode` quyết định context bao gồm mô-đun đang kiểm thử và những dependency mô-đun nào. Chọn đúng phạm vi giúp test phản ánh mục tiêu kiểm thử, đồng thời giữ thời gian khởi động và độ phức tạp ở mức phù hợp.

## 1. Xác định mô-đun đang được kiểm thử

Giả sử ứng dụng bán hàng có các mô-đun `orders`, `inventory` và `customers`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   └── OrderRepository.java
├── inventory
│   └── Inventory.java
└── customers
    └── CustomerLookup.java
```

Mỗi package mô-đun có thể chứa service, domain logic và adapter nội bộ. `orders` có thể phụ thuộc vào API của `inventory` và `customers`. Khi viết module test cho `orders`, đặt lớp test trong package của mô-đun đó hoặc package con để Spring Modulith xác định đúng module under test.

Ví dụ, test được đặt trong `src/test/java/com/acme/shop/orders/OrderModuleTests.java`:

```java
package com.acme.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderModuleTests {
    // Các test ở đây thuộc module orders.
}
```

`@ApplicationModuleTest` sử dụng package của lớp test để xác định mô-đun cần khởi tạo. Ứng dụng vẫn cần có lớp cấu hình Spring Boot ở package gốc phù hợp, chẳng hạn `ShopApplication` trong `com.acme.shop`. Đặt test đúng package giúp phạm vi được xác định rõ ràng và tránh vô tình kiểm thử nhầm một mô-đun khác.

## 2. Chọn BootstrapMode theo mục tiêu

`@ApplicationModuleTest` cung cấp ba chế độ bootstrap phổ biến:

| Chế độ | Context bao gồm | Phù hợp khi |
|---|---|---|
| `STANDALONE` | Chỉ mô-đun đang kiểm thử | Muốn kiểm thử hành vi mô-đun độc lập và thay dependency bên ngoài bằng test double |
| `DIRECT_DEPENDENCIES` | Mô-đun đang kiểm thử cùng các mô-đun mà nó phụ thuộc trực tiếp | Muốn kiểm tra tương tác thật với các dependency trực tiếp |
| `ALL_DEPENDENCIES` | Mô-đun đang kiểm thử cùng toàn bộ dependency trực tiếp và bắc cầu của nó | Use case cần nhiều mô-đun trong dependency graph hoạt động cùng nhau |

Khai báo chế độ tường minh giúp người đọc hiểu test đang yêu cầu phạm vi context nào:

```java
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderModuleTests {
}
```

Nếu dùng `STANDALONE`, các bean của mô-đun khác không được nạp như dependency thật trong context module test. Hãy cung cấp mock hoặc test double cho những collaborator mà bean của mô-đun đang kiểm thử cần. Với hai chế độ còn lại, Spring Modulith bổ sung các mô-đun phụ thuộc vào context theo phạm vi đã chọn.

Không phải test nào cũng cần `ALL_DEPENDENCIES`. Chế độ này có thể kéo theo nhiều bean, cấu hình và hạ tầng, khiến context gần với toàn ứng dụng. Chỉ chọn khi hành vi cần kiểm thử thực sự đi qua các dependency bắc cầu đó.

## 3. STANDALONE: kiểm thử mô-đun với dependency giả lập

Giả sử `OrderService` cần API `Inventory` để kiểm tra tồn kho:

```java
package com.acme.shop.inventory;

public interface Inventory {

    boolean isAvailable(String productId, int quantity);
}
```

Service thuộc mô-đun `orders`:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.Inventory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Inventory inventory;

    public OrderService(Inventory inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String productId, int quantity) {
        return inventory.isAvailable(productId, quantity);
    }
}
```

Trong standalone module test, dùng `@MockitoBean` để cung cấp collaborator giả lập:

```java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

import com.acme.shop.inventory.Inventory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderModuleTests {

    @Autowired OrderService orders;

    @MockitoBean Inventory inventory;

    @Test
    void checksAvailabilityBeforePlacingOrder() {
        given(inventory.isAvailable("sku-1", 2)).willReturn(true);

        assertThat(orders.canPlaceOrder("sku-1", 2)).isTrue();
    }
}
```

Test này khởi tạo bean thuộc `orders` và thay collaborator `Inventory` bằng Mockito mock. Nó tập trung kiểm tra cách `OrderService` sử dụng hợp đồng tồn kho, không phụ thuộc vào database hoặc implementation thật của `inventory`.

`@MockitoBean` thuộc Spring Test và có trong các phiên bản Spring Framework mới. Với dự án Spring Boot cũ chưa có annotation này, có thể dùng `@MockBean` tương ứng của Spring Boot test. Hãy chọn annotation theo phiên bản framework của dự án.

Standalone không có nghĩa là chỉ kiểm thử một lớp Java. Context vẫn có thể khởi tạo nhiều bean, repository hoặc cấu hình thuộc chính mô-đun `orders`. Mục tiêu là giới hạn module context ở mô-đun đó và kiểm soát các collaborator bên ngoài.

## 4. DIRECT_DEPENDENCIES: nạp các mô-đun phụ thuộc trực tiếp

Khi cần kiểm tra tương tác thật giữa `orders` và `inventory`, có thể nạp thêm dependency trực tiếp:

```java
package com.acme.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderWithInventoryTests {

    // Các bean thuộc orders và các module dependency trực tiếp được nạp.
}
```

Trong chế độ này, nếu `orders` phụ thuộc trực tiếp vào `inventory`, bean thuộc hai mô-đun có thể cùng tham gia context. Test có thể kiểm tra luồng gọi API thật giữa `OrderService` và implementation của `Inventory`, thay vì thay `Inventory` bằng mock.

Giả sử `orders` còn phụ thuộc trực tiếp vào `customers`, cả hai dependency trực tiếp đó cũng thuộc phạm vi bootstrap. Các dependency bắc cầu mà `inventory` hoặc `customers` cần không nhất thiết được nạp chỉ vì chúng là dependency của các mô-đun đó. Nếu context thiếu một bean bắc cầu, hãy đánh giá xem test cần `ALL_DEPENDENCIES`, cần cung cấp test double, hay đang kéo theo một quan hệ phụ thuộc không phù hợp.

## 5. ALL_DEPENDENCIES: nạp toàn bộ dependency bắc cầu

Một use case có thể cần nhiều mô-đun cùng hoạt động. Ví dụ, tạo đơn hàng cần `orders`, kiểm tra `inventory`, tra cứu `customers` và một mô-đun khác mà các dependency đó sử dụng. Khi cần kiểm thử luồng tích hợp xuyên qua toàn bộ dependency graph của mô-đun đích, dùng `ALL_DEPENDENCIES`:

```java
package com.acme.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.ALL_DEPENDENCIES
)
class OrderWorkflowTests {

    // Context bao gồm orders và toàn bộ dependency bắc cầu của nó.
}
```

Chế độ này hữu ích khi cần kiểm tra tương tác thật qua nhiều mô-đun, nhưng context có thể lớn hơn đáng kể. Nó vẫn được xác định từ dependency graph của mô-đun đang kiểm thử; không nên mặc định coi đây là cách nạp toàn bộ mọi mô-đun trong ứng dụng bất kể có quan hệ phụ thuộc hay không.

Nếu mục tiêu là kiểm thử một use case toàn ứng dụng, bao gồm cả các mô-đun không nằm trong dependency graph của `orders`, một integration test với `@SpringBootTest` có thể phù hợp hơn.

## 6. So sánh module test với SpringBootTest và test slice

Các loại test có phạm vi và mục tiêu khác nhau:

| Loại test | Phạm vi điển hình | Mục tiêu |
|---|---|---|
| Unit test thuần | Một lớp hoặc một nhóm lớp, không khởi tạo Spring context | Kiểm tra logic nhanh bằng dependency được truyền trực tiếp |
| `@ApplicationModuleTest` | Một mô-đun và dependency theo `BootstrapMode` | Kiểm tra hành vi và tích hợp ở ranh giới mô-đun |
| `@SpringBootTest` | ApplicationContext toàn ứng dụng theo cấu hình test | Kiểm tra tích hợp xuyên ứng dụng hoặc wiring toàn hệ thống |
| `@WebMvcTest`, `@DataJpaTest` | Một lát cắt MVC hoặc JPA | Kiểm tra một tầng framework với context nhỏ hơn |

Một dự án có thể dùng kết hợp các loại test. Unit test bao phủ logic thuần; module test kiểm tra hợp đồng và tương tác ở phạm vi mô-đun; full integration test kiểm tra các luồng xuyên ứng dụng. Test slice tập trung vào cấu hình của một công nghệ cụ thể.

Không nên dùng `@SpringBootTest` cho mọi tình huống chỉ vì nó dễ thiết lập. Context toàn ứng dụng thường khởi động chậm hơn và khiến test phụ thuộc vào nhiều cấu hình không liên quan tới hành vi đang kiểm tra. Ngược lại, không nên ép một test chỉ dùng standalone nếu mục tiêu của nó là xác minh sự phối hợp thực tế giữa nhiều mô-đun.

## 7. Chọn phạm vi context theo câu hỏi cần trả lời

Trước khi chọn mode, hãy viết câu hỏi mà test cần trả lời:

| Câu hỏi kiểm thử | Lựa chọn phù hợp | Cách xử lý dependency |
|---|---|---|
| Service của `orders` xử lý kết quả từ `Inventory` đúng không? | `STANDALONE` | Mock `Inventory` và kiểm soát kết quả trả về |
| `orders` gọi API thật của `inventory` đúng không? | `DIRECT_DEPENDENCIES` | Nạp bean thật của dependency trực tiếp |
| Use case của `orders` hoạt động qua các dependency bắc cầu không? | `ALL_DEPENDENCIES` | Nạp toàn bộ dependency trong graph của `orders` |
| Một luồng cần cả những mô-đun không nằm trong dependency graph của `orders` hoạt động cùng nhau không? | `@SpringBootTest` | Khởi tạo context toàn ứng dụng và cấu hình test cần thiết |
| Logic tính giá không cần Spring có đúng không? | Unit test | Tạo đối tượng trực tiếp và truyền collaborator giả |

Một cách chọn thực tế là bắt đầu với context nhỏ nhất có thể trả lời câu hỏi. Chỉ mở rộng mode khi test cần bean thật từ mô-đun khác hoặc khi một dependency bắc cầu là một phần của hành vi đang kiểm thử.

## 8. Context caching và thời gian chạy test

Spring TestContext có thể cache `ApplicationContext` giữa các test có cấu hình tương thích. Tuy nhiên, mỗi mode bootstrap hoặc tập bean override khác nhau có thể tạo ra context riêng. Vì vậy, một suite có nhiều tổ hợp module test, mode và mock có thể khởi động nhiều context hơn dự kiến.

Để giữ suite dễ bảo trì:

1. Gom các test có cùng module, mode và cấu hình chung khi điều đó làm test dễ hiểu hơn.
2. Dùng standalone cho các hành vi cần mock dependency bên ngoài, tránh nạp module khác không cần thiết.
3. Dùng `DIRECT_DEPENDENCIES` khi cần kiểm tra hợp đồng tích hợp thật với các dependency trực tiếp.
4. Dùng `ALL_DEPENDENCIES` có chọn lọc vì context có thể chứa nhiều bean và cấu hình.
5. Hạn chế thay đổi cấu hình context hoặc mock bean không cần thiết giữa các lớp test.
6. Nếu test dùng chung dữ liệu hoặc trạng thái có thể thay đổi, thiết lập và dọn dữ liệu rõ ràng để tránh phụ thuộc thứ tự chạy.

Không nên tối ưu cache bằng cách gộp các test có mục tiêu khác nhau vào một context lớn. Phạm vi context phải tiếp tục phản ánh câu hỏi kiểm thử.

## 9. Những lưu ý khi module test thất bại

**Không tìm thấy bean dependency.** Nếu dùng `STANDALONE`, kiểm tra xem collaborator thuộc mô-đun khác đã được thay bằng mock hoặc test double chưa. Nếu test cần implementation thật, cân nhắc `DIRECT_DEPENDENCIES`.

**Thiếu dependency bắc cầu.** Nếu mô-đun trực tiếp được nạp nhưng một bean của nó cần thêm module khác, đánh giá `ALL_DEPENDENCIES` hoặc thay dependency không liên quan bằng test double. Đừng mở rộng context chỉ để sửa một lỗi không thuộc mục tiêu test.

**Có nhiều bean cùng kiểu.** Dùng `@Qualifier`, `@Primary` hoặc cấu hình test rõ ràng để chọn implementation. Nếu đây là lỗi wiring thật trong production, hãy giữ test đủ gần cấu hình production để phát hiện vấn đề.

**Test chạy qua nhưng kiến trúc vẫn sai.** `@ApplicationModuleTest` xác minh hành vi runtime trong context đã chọn; nó không thay thế `ApplicationModules.verify()`. Giữ một architecture test riêng để kiểm tra module graph, package API và dependency rules.

**Context quá lớn hoặc khởi động chậm.** Xem lại mode, bean override và cấu hình test. Có thể test đang dùng `ALL_DEPENDENCIES` trong khi chỉ cần một module dependency trực tiếp hoặc một mock.

## 10. Bài tập tự kiểm tra

Với mô-đun `orders` có dependency trực tiếp tới `inventory` và `customers`, trong đó `inventory` còn phụ thuộc vào một mô-đun khác, hãy chọn mode cho từng mục tiêu:

| Mục tiêu | Mode hoặc loại test | Giải thích |
|---|---|---|
| Kiểm tra `OrderService` xử lý đúng khi tồn kho trả về `true` hoặc `false` | `STANDALONE` | Mock API `Inventory` và kiểm soát từng tình huống |
| Kiểm tra `OrderService` phối hợp với bean thật của `inventory` | `DIRECT_DEPENDENCIES` | Nạp dependency trực tiếp của `orders` |
| Kiểm tra luồng cần cả dependency mà `inventory` sử dụng | `ALL_DEPENDENCIES` | Nạp dependency bắc cầu của `orders` |
| Kiểm tra một use case toàn ứng dụng có liên quan tới mô-đun ngoài dependency graph | `@SpringBootTest` | Cần context toàn ứng dụng |

Hãy viết một test standalone cho `OrderService`, thay `Inventory` bằng mock và xác nhận kết quả với hai trường hợp có hàng và hết hàng. Sau đó viết một test dùng `DIRECT_DEPENDENCIES` để kiểm tra tích hợp với implementation thật của `inventory`. So sánh thời gian khởi động, số bean được nạp và mức độ phụ thuộc của hai test. Cuối cùng, giữ `ApplicationModules.verify()` trong architecture test riêng để kiểm tra các quy tắc boundary của ứng dụng.
