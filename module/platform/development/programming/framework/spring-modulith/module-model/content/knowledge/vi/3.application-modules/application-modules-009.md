# Giữ model trong test để kiểm tra lặp lại

Khi kiểm tra kiến trúc modular monolith, ta thường cần thực hiện nhiều nhận định trên cùng một cấu trúc module: xác nhận không có chu trình phụ thuộc, kiểm tra một module có tồn tại, quan sát danh sách module hoặc kiểm tra một quy tắc kiến trúc cụ thể. Nếu mỗi bài kiểm thử đều tự tạo lại mô hình bằng `ApplicationModules.of(ShopApplication.class)`, các bài kiểm thử sẽ lặp lại cùng một bước phân tích codebase.

Ta có thể tạo mô hình một lần trong phạm vi kiểm thử rồi giữ nó trong một trường dùng chung. Những bài kiểm thử liên quan cùng đọc một đối tượng `ApplicationModules`, nhờ đó cách kiểm tra nhất quán hơn và tránh thực hiện lại việc khám phá module không cần thiết.

Bài học này tập trung vào cách lưu giữ mô hình trong test, lựa chọn phạm vi chia sẻ và tổ chức các kiểm tra lặp lại. Mục tiêu là để ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package được kiểm tra tự động mỗi khi bộ kiểm thử chạy.

## 1. Vì sao nên giữ lại mô hình?

`ApplicationModules.of(...)` phân tích package và metadata kiến trúc để tạo mô hình module trong bộ nhớ. Đây là bước chuẩn bị cho các thao tác như duyệt module, tra cứu module và gọi `verify()`.

Giả sử ứng dụng bán hàng có ba module `catalog`, `orders` và `customers`. Nhóm muốn kiểm tra nhiều điều:

- Toàn bộ module tuân thủ quy tắc kiến trúc.
- Module `orders` được nhận diện trong mô hình.
- Mô hình có thể duyệt được để phục vụ các kiểm tra hoặc báo cáo khác.
- Các kiểm tra kiến trúc khác trong cùng bộ test sử dụng chung một điểm bắt đầu.

Nếu mỗi phương thức test đều gọi `ApplicationModules.of(ShopApplication.class)`, nhóm sẽ lặp lại bước tạo mô hình:

~~~java
@Test
void verifiesArchitecture() {
    ApplicationModules.of(ShopApplication.class).verify();
}

@Test
void containsOrdersModule() {
    ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

    assertTrue(modules.getModuleByName("orders").isPresent());
}
~~~

Cách viết trên vẫn đúng về mặt ý tưởng, nhưng mỗi test tự quyết định điểm bắt đầu và tự tạo mô hình riêng. Khi có nhiều kiểm tra, việc khởi tạo lặp lại làm code dài hơn và có thể tăng thời gian chạy.

Thay vào đó, ta tạo mô hình một lần và giữ trong một trường:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    private static final ApplicationModules MODULES =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesArchitecture() {
        MODULES.verify();
    }

    @Test
    void containsOrdersModule() {
        assertTrue(MODULES.getModuleByName("orders").isPresent());
    }
}
~~~

Trường `static final` được khởi tạo một lần khi lớp test được nạp. Các phương thức test trong lớp cùng sử dụng đối tượng đó. Mỗi test vẫn thực hiện một kiểm tra độc lập, nhưng phần chuẩn bị mô hình được tập trung tại một nơi.

## 2. Giữ mô hình trong một lớp test

Đây là cách đơn giản nhất khi các kiểm tra kiến trúc nằm trong cùng một lớp JUnit 5.

~~~java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    private static final ApplicationModules MODULES =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesModuleStructure() {
        MODULES.verify();
    }

    @Test
    void containsOrdersModule() {
        assertTrue(MODULES.getModuleByName("orders").isPresent());
    }

    @Test
    void containsCatalogModule() {
        assertTrue(MODULES.getModuleByName("catalog").isPresent());
    }
}
~~~

Trong ví dụ này:

1. `ApplicationModules.of(ShopApplication.class)` tạo mô hình dựa trên lớp ứng dụng.
2. Trường `MODULES` giữ tham chiếu đến mô hình trong suốt vòng đời của lớp test.
3. Test `verifiesModuleStructure()` gọi `verify()` để kiểm tra quy tắc kiến trúc.
4. Các test khác tra cứu module từ cùng mô hình.

Mỗi phương thức test chỉ thể hiện điều nó muốn xác nhận. Việc chọn lớp ứng dụng và tạo mô hình được khai báo tập trung, nên khi điểm bắt đầu ứng dụng thay đổi, nhóm chỉ cần cập nhật một vị trí.

Nếu dùng JUnit 5, ta cũng có thể đặt phần chuẩn bị trong `@BeforeAll`:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    private static ApplicationModules modules;

    @BeforeAll
    static void createModuleModel() {
        modules = ApplicationModules.of(ShopApplication.class);
    }

    @Test
    void verifiesModuleStructure() {
        modules.verify();
    }

    @Test
    void containsOrdersModule() {
        assertTrue(modules.getModuleByName("orders").isPresent());
    }
}
~~~

`@BeforeAll` chạy một lần trước các test trong lớp. Phương thức này phải là `static` theo mặc định của JUnit Jupiter. Nếu dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, JUnit cho phép `@BeforeAll` là phương thức instance; tuy nhiên, trường `static final` thường ngắn gọn hơn khi mô hình không cần thay đổi.

Không nên vừa tạo mô hình trong `@BeforeAll` vừa tạo thêm một mô hình khác trong từng test. Hãy chọn một cách khởi tạo rõ ràng để tất cả kiểm tra trong lớp dùng chung cùng một điểm bắt đầu.

## 3. Chia sẻ mô hình giữa nhiều lớp test

Khi bộ kiểm thử lớn hơn, nhóm có thể tách kiểm tra theo mục đích: một lớp kiểm tra cấu trúc tổng thể, một lớp kiểm tra danh sách module và một lớp kiểm tra các quy tắc riêng. Nếu mỗi lớp lại tự gọi `ApplicationModules.of(...)`, cách tổ chức vẫn bị lặp.

Có thể đặt mô hình trong một lớp hỗ trợ package-private ở thư mục test:

~~~java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModules;

final class ModulithTestModel {

    static final ApplicationModules MODULES =
        ApplicationModules.of(ShopApplication.class);

    private ModulithTestModel() {
    }
}
~~~

Sau đó, các lớp test dùng chung trường `MODULES`:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;

class ModuleArchitectureTests {

    @Test
    void verifiesAllModuleRules() {
        ModulithTestModel.MODULES.verify();
    }
}
~~~

~~~java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ModuleInventoryTests {

    @Test
    void ordersModuleIsPresent() {
        assertTrue(
            ModulithTestModel.MODULES
                .getModuleByName("orders")
                .isPresent()
        );
    }

    @Test
    void catalogModuleIsPresent() {
        assertTrue(
            ModulithTestModel.MODULES
                .getModuleByName("catalog")
                .isPresent()
        );
    }
}
~~~

Cả hai lớp test truy cập cùng một mô hình thông qua `ModulithTestModel.MODULES`. Nhóm có thể mở rộng lớp hỗ trợ này khi cần một điểm khởi tạo thống nhất cho các kiểm tra kiến trúc.

Mô hình dùng chung nên nằm trong source set test, chẳng hạn `src/test/java`, vì đây là công cụ phục vụ kiểm thử. Không cần đưa lớp hỗ trợ hoặc trường mô hình vào mã production của ứng dụng.

Một lựa chọn khác là tạo lớp cơ sở dành cho các test kiến trúc và khai báo trường `protected static final` để lớp con sử dụng. Tuy nhiên, một lớp hỗ trợ có trường `static final` thường thể hiện quan hệ dùng chung rõ ràng hơn và tránh tạo hệ thống kế thừa chỉ để chia sẻ một đối tượng.

## 4. Kết hợp nhiều kiểm tra trên cùng một model

Sau khi giữ mô hình, ta có thể tổ chức các test theo từng mối quan tâm mà không phải tạo lại đối tượng.

Ví dụ, lớp test có thể vừa kiểm tra toàn bộ quy tắc vừa kiểm tra một số đặc điểm của mô hình:

~~~java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    private static final ApplicationModules MODULES =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesModuleStructure() {
        MODULES.verify();
    }

    @Test
    void discoversExpectedModules() {
        assertTrue(MODULES.getModuleByName("catalog").isPresent());
        assertTrue(MODULES.getModuleByName("orders").isPresent());
        assertTrue(MODULES.getModuleByName("customers").isPresent());
    }

    @Test
    void exposesIterableModel() {
        assertTrue(MODULES.iterator().hasNext());
    }

    @Test
    void exposesStreamModel() {
        assertTrue(MODULES.stream().count() > 0);
    }
}
~~~

Các test minh họa bốn cách sử dụng:

| Kiểm tra | Câu hỏi được trả lời |
|---|---|
| `verify()` | Cấu trúc module có tuân thủ quy tắc kiến trúc không? |
| `getModuleByName()` | Module mong đợi có được nhận diện không? |
| `iterator()` | Có thể duyệt các module trong mô hình không? |
| `stream()` | Có thể dùng Stream API để quan sát tập module không? |

Các kiểm tra về sự hiện diện của module không thay thế `verify()`. Một module có thể được nhận diện nhưng vẫn phụ thuộc sai vào package nội bộ hoặc tham gia vào chu trình phụ thuộc. Vì vậy, hãy giữ test kiểm chứng kiến trúc như một phần của bộ test.

Ngược lại, `verify()` cũng không thay thế mọi assertion về ý định của ứng dụng. Nếu nhóm yêu cầu phải có module `orders`, một assertion riêng về sự hiện diện của module diễn đạt yêu cầu đó trực tiếp hơn.

## 5. Tổ chức kiểm tra lặp lại trong CI

Giá trị của việc giữ mô hình thể hiện rõ nhất khi kiểm tra kiến trúc trở thành một phần ổn định của quy trình build.

Một bài test kiến trúc nên được chạy cùng các test tự động khác:

~~~text
Thay đổi mã nguồn
      |
      v
Chạy test suite
      |
      v
Tạo ApplicationModules model
      |
      +--> Kiểm tra module mong đợi
      |
      +--> Kiểm tra các quy tắc bằng verify()
      |
      v
Báo kết quả cho CI
      |
      +--> PASS: tiếp tục pipeline
      |
      +--> FAIL: xem vi phạm và sửa kiến trúc
~~~

Khi có thay đổi làm phát sinh phụ thuộc không hợp lệ, test `verify()` sẽ thất bại. Nhóm có thể xem thông báo vi phạm để xác định module nào truy cập vào package nội bộ hoặc quan hệ phụ thuộc nào tạo thành chu trình.

Nên đặt tên test theo điều kiện kiến trúc mà nó bảo vệ, ví dụ `verifiesModuleStructure` hoặc `ordersModuleIsPresent`. Tên rõ ràng giúp log CI cho biết loại quy tắc nào đang được kiểm tra.

Nếu dự án có nhiều lớp kiểm tra, có thể gom các test liên quan vào một package hoặc một nhóm test kiến trúc. Điều quan trọng là mọi test đều sử dụng cùng lớp ứng dụng làm điểm bắt đầu, để kết quả giữa các lần kiểm tra có thể so sánh và giải thích được.

## 6. Phạm vi vòng đời của model dùng chung

Trường `static final` không có nghĩa mô hình tồn tại vĩnh viễn. Nó chỉ được giữ trong vòng đời của lớp được nạp trong một JVM và classloader tương ứng.

Một số điểm cần lưu ý:

- Trong cùng một lớp test, trường `static final` được khởi tạo một lần khi lớp được nạp.
- Nếu nhiều lớp test dùng một lớp hỗ trợ chung, trường static của lớp hỗ trợ được khởi tạo khi lớp hỗ trợ được nạp trong classloader đó.
- Nếu build chạy test ở các JVM hoặc fork riêng, mỗi tiến trình có vòng đời và bản sao mô hình riêng.
- Khi chạy một lượt test mới với classpath mới, mô hình sẽ được tạo lại từ codebase và môi trường của lượt chạy đó.

Vì vậy, việc giữ mô hình dùng chung giúp tránh phân tích lặp lại trong phạm vi phù hợp, nhưng không tạo một cache bền vững giữa các lần build.

Mô hình cũng phản ánh cấu trúc và metadata tại thời điểm được tạo. Nếu một test thay đổi classpath, cấu hình phát hiện module hoặc dữ liệu đầu vào khiến phạm vi phân tích khác đi, không nên tiếp tục dùng đối tượng cũ để đại diện cho trạng thái mới. Hãy tạo mô hình mới trong lượt kiểm tra có môi trường tương ứng.

`ApplicationModules` là mô hình kiến trúc trong bộ nhớ, không phải `ApplicationContext` của Spring. Giữ mô hình trong test không đồng nghĩa giữ một Spring container đang chạy và không yêu cầu khởi động toàn bộ ứng dụng để gọi các API phân tích module.

## 7. Những lỗi thường gặp khi tái sử dụng model

**Tạo model ở nhiều nơi mà không có lý do.** Nếu các test cùng kiểm tra một ứng dụng với cùng package gốc, hãy dùng chung một điểm khởi tạo. Nhiều trường static độc lập có thể khiến nhóm khó biết test nào đang dùng cấu hình nào.

**Dùng sai lớp ứng dụng làm mốc.** `ApplicationModules.of(...)` phân tích phạm vi từ lớp hoặc package được truyền vào. Nếu một test dùng lớp ứng dụng khác, mô hình có thể mô tả một phạm vi khác. Hãy thống nhất lớp khởi động đại diện cho ứng dụng cần kiểm tra.

**Chỉ kiểm tra module tồn tại.** Việc tra cứu thành công không chứng minh ranh giới module hợp lệ. Hãy giữ một test gọi `verify()` để kiểm tra các quy tắc kiến trúc.

**Đưa test fixture vào production.** Mô hình được giữ để phục vụ kiểm thử nên lớp hỗ trợ nên nằm trong source set test. Mã production không cần phụ thuộc vào cấu trúc fixture của JUnit.

**Xem model như trạng thái runtime luôn cập nhật.** Đối tượng không tự quét lại codebase sau khi đã tạo. Khi cần phân tích trạng thái mới, hãy tạo đối tượng mới trong lần chạy phù hợp.

**Chia sẻ mutable state giữa các test.** Mô hình dùng chung nên được xem là dữ liệu phân tích để đọc và kiểm chứng. Tránh gắn thêm trạng thái có thể thay đổi theo từng test vào fixture chung, vì điều đó làm các test ảnh hưởng lẫn nhau.

## Kết luận

Giữ một đối tượng `ApplicationModules` trong test giúp nhiều kiểm tra kiến trúc sử dụng cùng một mô hình được tạo từ cùng một điểm bắt đầu. Với một lớp test, có thể dùng trường `static final` hoặc khởi tạo trong `@BeforeAll`. Khi nhiều lớp test cần dùng chung, có thể đặt mô hình trong một lớp hỗ trợ thuộc source set test.

Từ mô hình dùng chung, nhóm có thể kiểm tra sự hiện diện của module, duyệt danh sách module và gọi `verify()` để bảo vệ ranh giới kiến trúc. Khi những kiểm tra này chạy thường xuyên trong CI, các quy tắc modular monolith được duy trì qua từng thay đổi của codebase thay vì chỉ được xác nhận tại thời điểm thiết kế.
