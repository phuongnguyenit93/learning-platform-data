# Chạy `ApplicationModules.verify()` trong test

## Mục tiêu

Trong một ứng dụng Spring Boot dạng modular monolith, các module nghiệp vụ thường nằm trong những package khác nhau của cùng một ứng dụng. Cách tổ chức package chỉ tạo ra ranh giới về mặt quy ước; Java vẫn cho phép một module tham chiếu trực tiếp đến nhiều lớp thuộc module khác. Vì vậy, một thay đổi tưởng như nhỏ có thể tạo ra phụ thuộc vòng hoặc làm lộ lớp triển khai nội bộ.

Spring Modulith cung cấp `ApplicationModules` để đọc cấu trúc module từ package của ứng dụng. Phương thức `verify()` kiểm tra cấu trúc đó theo các quy tắc kiến trúc của Spring Modulith. Khi đặt lời gọi này trong một bài kiểm thử JUnit, mỗi lần chạy test hoặc build đều có thể phát hiện sớm những phụ thuộc làm sai ranh giới module.

Sau bài thực hành, bạn có thể:

- Thêm dependency kiểm thử Spring Modulith vào dự án.
- Tạo một bài kiểm thử kiến trúc bằng `ApplicationModules.of(...).verify()`.
- Chạy riêng bài kiểm thử hoặc chạy cùng toàn bộ test suite.
- Đọc lỗi xác minh và sửa phụ thuộc giữa các module.
- Đưa kiểm tra kiến trúc vào quy trình build liên tục.

## 1. Chuẩn bị cấu trúc ứng dụng

Giả sử ứng dụng cửa hàng có package gốc `com.acme.shop` và ba module nghiệp vụ là `orders`, `inventory`, `payments`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── package-info.java
│   ├── OrderService.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── package-info.java
│   ├── InventoryReservation.java
│   └── internal
│       └── StockRepository.java
└── payments
    ├── package-info.java
    └── PaymentAuthorization.java
```

Lớp khởi động nằm tại package gốc:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Theo cách phát hiện module mặc định, các package con trực tiếp của package gốc như `orders`, `inventory` và `payments` được nhận diện là các module. Package con sâu hơn có thể chứa phần triển khai nội bộ của module tương ứng.

Ví dụ, `com.acme.shop.inventory.InventoryReservation` nằm trong package gốc của module `inventory` và có thể được dùng làm API của module. Trong khi đó, `com.acme.shop.inventory.internal.StockRepository` thuộc package nội bộ. Một module khác không nên phụ thuộc trực tiếp vào lớp nội bộ này.

## 2. Thêm dependency kiểm thử

Thêm starter kiểm thử của Spring Modulith vào cấu hình build. Dependency này được khai báo trong phạm vi test vì ta chỉ cần kiểm tra mô hình module khi chạy kiểm thử.

Với Maven, thêm vào `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
```

Hãy dùng phiên bản Spring Modulith tương thích với phiên bản Spring Boot của dự án. Nếu dự án quản lý phiên bản bằng Spring Modulith BOM hoặc dependency management của Spring Boot, giữ dependency không kèm phiên bản để cơ chế quản lý phiên bản đã cấu hình chọn phiên bản phù hợp.

Sau khi thêm dependency, đồng bộ lại Maven hoặc Gradle để lớp kiểm thử có thể import `ApplicationModules`.

## 3. Tạo bài kiểm thử kiến trúc

Tạo lớp `ApplicationModuleVerificationTests` trong source set test. Đặt lớp test trong package gốc hoặc import chính xác lớp ứng dụng gốc.

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleVerificationTests {

    private final ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesApplicationModuleStructure() {
        modules.verify();
    }
}
```

Điểm quan trọng của bài test nằm ở hai lời gọi:

1. `ApplicationModules.of(ShopApplication.class)` tạo mô hình module dựa trên package của lớp ứng dụng được truyền vào. Hãy truyền lớp có `@SpringBootApplication` ở package gốc để Spring Modulith quét đúng phạm vi.
2. `modules.verify()` yêu cầu Spring Modulith kiểm tra mô hình theo các quy tắc kiến trúc hiện có. Nếu phát hiện vi phạm, phương thức sẽ làm bài test thất bại và đưa thông tin vi phạm vào kết quả kiểm thử.

Bài kiểm thử này không cần `@SpringBootTest`: mục tiêu của nó là xác minh cấu trúc module, không phải khởi động Spring ApplicationContext để kiểm tra hành vi của một luồng nghiệp vụ. Các bài integration test vẫn có vai trò riêng và có thể được viết bên cạnh bài kiểm thử kiến trúc này.

## 4. Chạy bài kiểm thử

Bạn có thể chạy riêng lớp kiểm thử để nhận phản hồi nhanh trong lúc thiết kế package.

Với Maven:

```bash
./mvnw -Dtest=ApplicationModuleVerificationTests test
```

Trên Windows, dùng `mvnw.cmd` thay cho `./mvnw`.

Với Gradle:

```bash
./gradlew test --tests "com.acme.shop.ApplicationModuleVerificationTests"
```

Trên Windows, dùng `gradlew.bat` thay cho `./gradlew`.

Khi cấu trúc hợp lệ, test `verifiesApplicationModuleStructure` sẽ thành công và build tiếp tục. Khi cấu trúc vi phạm quy tắc, test thất bại; xem phần lỗi của test hoặc báo cáo test do Maven/Gradle tạo ra để biết module nào đang phụ thuộc sai.

Sau khi test riêng chạy ổn định, hãy chạy toàn bộ test suite bằng `./mvnw test` hoặc `./gradlew test`. Như vậy, kiểm tra kiến trúc sẽ trở thành một phần của cùng quy trình xác minh mà nhóm phát triển vẫn chạy trước khi tích hợp thay đổi.

## 5. Quan sát một vi phạm về API module

Giả sử `OrderService` cần giữ chỗ tồn kho. Cách phụ thuộc phù hợp là gọi API được module `inventory` công khai, chẳng hạn `InventoryReservation`:

```java
package com.acme.shop.inventory;

public interface InventoryReservation {

    void reserve(String productId, int quantity);
}
```

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.InventoryReservation;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final InventoryReservation inventoryReservation;

    public OrderService(InventoryReservation inventoryReservation) {
        this.inventoryReservation = inventoryReservation;
    }

    public void reserveInventory(String productId, int quantity) {
        inventoryReservation.reserve(productId, quantity);
    }
}
```

Tên phương thức trong ví dụ minh họa một API nghiệp vụ; trong dự án thực tế, chữ ký phương thức cần khớp với lớp API mà module `inventory` cung cấp.

Bây giờ thử thay import API bằng lớp repository nội bộ:

```java
import com.acme.shop.inventory.internal.StockRepository;
```

Giả sử `StockRepository` là một lớp `public` trong package `inventory.internal`, để mã Java có thể biên dịch khi module khác import nó. Nếu `OrderService` sử dụng trực tiếp lớp này, module `orders` đã đi xuyên qua ranh giới của `inventory` để truy cập chi tiết triển khai. Chạy lại `ApplicationModuleVerificationTests`. Spring Modulith có thể báo rằng module `orders` đang truy cập một kiểu thuộc package nội bộ của module `inventory`.

Để sửa, đưa thao tác cần thiết thành một API nghiệp vụ ở package công khai của `inventory`, rồi để chính module `inventory` gọi `StockRepository` bên trong nó. `orders` chỉ phụ thuộc vào API đó. Chạy lại test để xác nhận vi phạm đã được loại bỏ.

Quy tắc này giúp module sở hữu dữ liệu và chi tiết triển khai có quyền thay đổi nội bộ mà không buộc các module gọi nó phải biết cách lưu trữ hoặc xử lý bên trong.

## 6. Quan sát phụ thuộc vòng giữa các module

Một loại vi phạm khác xuất hiện khi hai module phụ thuộc trực tiếp lẫn nhau. Ví dụ:

```text
orders ───────► payments
   ▲               │
   └───────────────┘
```

Giả sử `OrderService` gọi `PaymentAuthorization`, đồng thời một lớp trong module `payments` lại import `Order` hoặc `OrderService` từ module `orders`. Hai hướng phụ thuộc tạo thành chu trình. Chu trình làm ranh giới module khó hiểu và khiến thay đổi ở một module dễ kéo theo thay đổi ở module còn lại.

Hãy chạy lại `ApplicationModuleVerificationTests` sau khi tạo tình huống này trong mã thử nghiệm. `verify()` sẽ phát hiện chu trình phụ thuộc module và làm test thất bại.

Để xử lý, xác định module nào nên điều phối nghiệp vụ và giữ một hướng phụ thuộc rõ ràng. Chẳng hạn, `orders` có thể gọi API thanh toán của `payments`; khi thanh toán hoàn tất, `payments` công bố sự kiện nghiệp vụ như `PaymentAuthorized`, còn `orders` lắng nghe sự kiện đó. Module `payments` không cần import ngược các lớp của `orders`. Sau khi bỏ phụ thuộc ngược, chạy lại test để kiểm tra đồ thị module đã hết chu trình.

Sự kiện chỉ là một phương án thiết kế khi nó phù hợp với luồng nghiệp vụ. Không nên chuyển mọi lời gọi đồng bộ thành sự kiện chỉ để làm test xanh; hãy chọn ranh giới và hướng phụ thuộc phản ánh đúng quyền sở hữu nghiệp vụ.

## 7. Khai báo các phụ thuộc được phép

Trong một số ứng dụng, nhóm muốn giới hạn rõ module nào được phép phụ thuộc vào module nào. Có thể khai báo `allowedDependencies` trên package của module bằng `@ApplicationModule`.

Ví dụ, nếu `orders` chỉ được phép phụ thuộc vào `inventory` và `payments`, tạo hoặc cập nhật `com.acme.shop.orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {"inventory", "payments"}
)
package com.acme.shop.orders;
```

Khi quy tắc này được khai báo, nếu một lớp trong `orders` bắt đầu phụ thuộc vào module khác ngoài danh sách, `modules.verify()` sẽ báo vi phạm. Điều đó biến danh sách phụ thuộc được phép thành một hợp đồng kiến trúc có thể kiểm tra tự động.

Nếu dự án sử dụng Named Interface để công khai một package con, hãy khai báo Named Interface ở package API bằng `@NamedInterface` và tham chiếu đúng tên interface trong quy tắc phụ thuộc. Cách này cho phép module công khai một phần API có chủ đích mà vẫn giữ các package con khác ở trạng thái nội bộ. Tên module và tên Named Interface trong cấu hình phải khớp với tên thực tế mà Spring Modulith nhận diện.

Ví dụ, nếu module `inventory` công khai package `com.acme.shop.inventory.api` dưới tên Named Interface `api`, package đó có thể khai báo:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Khi `orders` chỉ được phép dùng Named Interface này, giá trị trong `allowedDependencies` có thể giới hạn ở `inventory::api`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Sau mỗi lần thay đổi `allowedDependencies` hoặc Named Interface, chạy lại bài test kiến trúc. Test cần xác nhận cả hai điều: các phụ thuộc hợp lệ vẫn được chấp nhận và các phụ thuộc ngoài hợp đồng bị từ chối.

## 8. Đọc lỗi và xử lý theo nguyên nhân

Khi `verify()` thất bại, hãy đọc tên module được nêu trong thông báo và đường dẫn kiểu hoặc package liên quan. Sau đó lần theo cạnh phụ thuộc từ module sử dụng đến module được sử dụng.

| Dấu hiệu trong lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Module truy cập kiểu trong package nội bộ của module khác | Một lớp đang import trực tiếp implementation hoặc repository nội bộ | Tạo hoặc sử dụng API công khai; chuyển lời gọi nội bộ về module sở hữu lớp đó |
| Các module tạo thành dependency cycle | Hai hay nhiều module tham chiếu lẫn nhau | Chọn một hướng phụ thuộc; cân nhắc sự kiện nghiệp vụ hoặc một API thuộc đúng module sở hữu khái niệm |
| Module phụ thuộc ngoài `allowedDependencies` | Mã nguồn tạo thêm một cạnh phụ thuộc chưa được cho phép | Xác nhận phụ thuộc có đúng về nghiệp vụ không; nếu hợp lệ, cập nhật hợp đồng có chủ đích, nếu không thì thiết kế lại lời gọi |
| Không nhận diện được module như mong đợi | Truyền sai lớp gốc hoặc package module không nằm trong phạm vi quét | Truyền lớp ứng dụng ở package gốc và kiểm tra lại cấu trúc package theo chiến lược phát hiện module đang dùng |

Không nên sửa lỗi bằng cách mở rộng API một cách tùy tiện hoặc thêm mọi module vào `allowedDependencies`. Trước tiên, xác định lý do module cần phụ thuộc. Nếu đó là nhu cầu nghiệp vụ hợp lệ, công khai đúng hợp đồng nhỏ nhất; nếu đó là truy cập nhầm chi tiết triển khai, sửa nơi gọi để giữ quyền sở hữu trong module.

## 9. Đưa kiểm tra kiến trúc vào quy trình phát triển

Sau khi tạo bài test, giữ nó trong source set test và đặt tên theo quy ước test của dự án để Maven hoặc Gradle tự động phát hiện. Mỗi pull request hoặc lần tích hợp cần chạy test suite sẽ đồng thời chạy xác minh module.

Một quy trình thực tế có thể gồm:

1. Nhà phát triển thay đổi mã nguồn của một module.
2. Chạy `ApplicationModuleVerificationTests` trong lúc phát triển để kiểm tra nhanh ranh giới module.
3. Chạy toàn bộ test suite trước khi tạo hoặc cập nhật pull request.
4. Pipeline CI chạy lại test suite và chặn build nếu `verify()` phát hiện vi phạm.

Hãy giữ bài kiểm thử kiến trúc độc lập với các test nghiệp vụ. Test nghiệp vụ xác minh kết quả của hành vi; bài test `ApplicationModules.verify()` xác minh cấu trúc phụ thuộc. Hai loại test bổ sung cho nhau.

## 10. Bài tập thực hành

Thực hiện trên ứng dụng cửa hàng có ba module `orders`, `inventory` và `payments`.

**Nhiệm vụ A — Tạo kiểm tra tự động**

1. Thêm `spring-modulith-starter-test` vào cấu hình build.
2. Tạo `ApplicationModuleVerificationTests` và gọi `ApplicationModules.of(ShopApplication.class).verify()` trong một phương thức `@Test`.
3. Chạy riêng test và ghi lại kết quả.

**Nhiệm vụ B — Kiểm tra quyền truy cập API**

1. Cho `orders` sử dụng một kiểu công khai trong package gốc `inventory`.
2. Chạy test và xác nhận cấu trúc hợp lệ.
3. Thử cho `orders` import một kiểu trong `inventory.internal`.
4. Chạy lại test, ghi nhận thông tin vi phạm và sửa bằng API công khai.

**Nhiệm vụ C — Kiểm tra phụ thuộc vòng**

1. Tạo phụ thuộc từ `orders` sang `payments`.
2. Tạm thời tạo thêm một phụ thuộc ngược từ `payments` sang `orders`.
3. Chạy test để quan sát lỗi chu trình.
4. Loại bỏ phụ thuộc ngược bằng cách điều chỉnh hợp đồng giữa hai module; nếu phù hợp với nghiệp vụ, thử dùng sự kiện do module thanh toán công bố.
5. Chạy lại test và xác nhận chu trình đã được loại bỏ.

**Nhiệm vụ D — Bảo vệ hợp đồng phụ thuộc**

1. Khai báo `allowedDependencies` cho module `orders`.
2. Tạo một phụ thuộc đến module không có trong danh sách và chạy test.
3. Quyết định phụ thuộc đó có hợp lệ về nghiệp vụ hay không; cập nhật thiết kế hoặc hợp đồng tương ứng.
4. Chạy toàn bộ test suite để xác nhận kiểm tra kiến trúc được thực thi cùng các test khác.

## 11. Tiêu chí hoàn thành

- Bài kiểm thử kiến trúc được Maven hoặc Gradle phát hiện và thực thi.
- Test thành công khi các module chỉ phụ thuộc theo hợp đồng đã thiết kế.
- Test thất bại khi có truy cập trái phép vào package nội bộ, phụ thuộc vòng hoặc phụ thuộc ngoài danh sách được phép.
- Sau khi sửa từng vi phạm, test chạy thành công trở lại.
- Toàn bộ test suite vẫn chạy được và bài kiểm thử kiến trúc được đưa vào quy trình CI của dự án.

Khi đạt các tiêu chí này, nhóm đã có một hàng rào tự động để bảo vệ ranh giới module. Mỗi thay đổi về package và phụ thuộc sẽ được kiểm tra ngay trong vòng đời test thông thường, giúp modular monolith duy trì cấu trúc rõ ràng khi ứng dụng phát triển.
