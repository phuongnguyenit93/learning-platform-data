# Không mở toàn bộ production module chỉ để test tiện hơn

Khi viết test cho ứng dụng sử dụng Java Platform Module System (JPMS), một cám dỗ phổ biến là đổi `module com.example.orders` thành `open module com.example.orders` để JUnit, Mockito hoặc framework kiểm thử có thể phản chiếu vào bất kỳ class, constructor hay field nào. Cách này có thể làm một số bài test chạy nhanh hơn, nhưng đồng thời **làm yếu ranh giới đóng gói của toàn bộ module production**.

Nguyên tắc cốt lõi: **quyền chỉ cần cho kiểm thử nên được cấp trong cấu hình kiểm thử**, không tự động trở thành hợp đồng truy cập của chương trình sản xuất. Hãy kiểm tra mục tiêu test trước, rồi chọn cách phù hợp: kiểm thử qua public API, patch test vào module, mở một package có giới hạn cho framework, hoặc tách một test-support API có chủ đích.

## 1. Vì sao JPMS làm test thay đổi?

Trong Java truyền thống, phần lớn class nằm trên classpath và thuộc unnamed module của class loader. Framework test thường dùng reflection để:

- Tìm class có `@Test` và tạo instance.
- Gọi test method không public.
- Đọc/ghi field trong test fixture.
- Gọi constructor hoặc method private qua `setAccessible(true)`.
- Tạo mock, proxy hoặc inject dependency.

Khi code production trở thành **named module**, các package có quyền truy cập theo module descriptor. Bên cạnh modifier `public`, `protected`, package-private và `private`, JPMS còn có:

- **Readability:** module nào được phép đọc module khác, thường khai báo bằng `requires`.
- **Exports:** package nào cho phép module khác sử dụng kiểu public theo cách Java thông thường.
- **Opens:** package nào cho phép module khác thực hiện deep reflection.

Vì vậy, test có thể thấy class trên module path nhưng vẫn không thể truy cập package hoặc thành viên cần dùng. Đây là hành vi đóng gói có chủ đích của JPMS, không phải lý do để mở toàn bộ production module.

## 2. Khác nhau giữa exports, opens và open module

Giả sử module production ban đầu:

    module com.example.orders {
        exports com.example.orders.api;
    }

Các package:

    com.example.orders.api
    com.example.orders.internal
    com.example.orders.persistence

Module bên ngoài có thể import các kiểu public trong `com.example.orders.api`, nhưng không tự được phép import kiểu trong `internal` hoặc `persistence`.

Có ba cơ chế thường bị nhầm:

| Cơ chế | Ý nghĩa | Tác động |
|---|---|---|
| `exports p;` | Cho các module khác truy cập kiểu public trong package p | Truy cập Java thông thường |
| `opens p;` | Mở package p cho deep reflection từ các module khác | Truy cập reflection ở runtime |
| `opens p to m;` | Mở riêng package p cho module m | Reflection có giới hạn đích |
| `open module X { ... }` | Mở tất cả package của module X cho deep reflection | Quyền reflection rất rộng |

`open module` **không làm tất cả package tự động được export để import trực tiếp**. Tuy vậy, nó cho phép các module khác thực hiện deep reflection vào mọi package thuộc module, kể cả package vốn dùng làm chi tiết triển khai.

Ví dụ không nên áp dụng chỉ để test thuận tiện:

    open module com.example.orders {
        exports com.example.orders.api;
    }

Cấu hình này khiến cả `api`, `internal` và `persistence` được mở cho deep reflection, trong khi test có thể chỉ cần truy cập một field của một class.

## 3. Rủi ro của việc mở toàn bộ production module

Việc chuyển sang `open module` ảnh hưởng mọi lần chạy module được đóng gói, không chỉ lúc test.

Các hệ quả:

1. **Mở rộng bề mặt phản chiếu:** code ở module khác có thể yêu cầu truy cập sâu vào nhiều package nội bộ hơn dự định.
2. **Làm mờ hợp đồng kiến trúc:** package nào là chi tiết triển khai và package nào là hợp đồng reflection không còn phân biệt rõ.
3. **Tạo phụ thuộc mong manh:** framework hoặc test có thể bắt đầu phụ thuộc vào field/constructor private dễ thay đổi.
4. **Che khuất vấn đề cấu hình:** một bài test đáng lẽ cần test-scoped `--add-opens` sẽ không còn bộc lộ ranh giới truy cập thực tế.
5. **Khác với mục tiêu migration JPMS:** module descriptor được tạo để diễn tả ranh giới phụ thuộc, không chỉ để qua bước biên dịch.

Đây không phải là tuyên bố mọi `open module` đều sai. Một module được thiết kế chủ ý cho reflection rộng, chẳng hạn một số kiểu mô hình dữ liệu phục vụ framework, có thể cần nó. Nhưng **sự tiện lợi của test đơn lẻ không phải là bằng chứng production cần mở tất cả package**.

## 4. Ưu tiên test hành vi qua public API

Nếu mục tiêu là xác minh hành vi của một module, nên bắt đầu từ API được export.

Ví dụ module production:

    module com.example.orders {
        exports com.example.orders.api;
    }

API:

    package com.example.orders.api;

    public final class OrderService {
        public int total(int price, int quantity) {
            if (price < 0 || quantity < 0) {
                throw new IllegalArgumentException();
            }
            return price * quantity;
        }
    }

JUnit test có thể chỉ cần:

    package com.example.orders.tests;

    import com.example.orders.api.OrderService;
    import org.junit.jupiter.api.Test;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertThrows;

    class OrderServiceTest {
        @Test
        void calculatesTotal() {
            assertEquals(150, new OrderService().total(50, 3));
        }

        @Test
        void rejectsNegativeQuantity() {
            assertThrows(IllegalArgumentException.class,
                () -> new OrderService().total(50, -1));
        }
    }

Mục tiêu của test là hợp đồng observable từ ngoài module. Test không cần biết class nội bộ nào đang thực hiện phép nhân hoặc field private nào lưu cache.

Nếu test nằm trong named module riêng, module test cần readability tới module production, và test framework có thể cần quyền reflection tới package chứa test class. Các yêu cầu này có thể được đáp ứng bằng **cấu hình test**, không phải mở mọi package production.

## 5. Test module riêng để kiểm tra ranh giới API

Một cách kiểm thử đúng kiến trúc JPMS là đặt các test API trong một named module riêng.

Production descriptor:

    module com.example.orders {
        exports com.example.orders.api;
    }

Descriptor minh họa của một module kiểm thử:

    module com.example.orders.contract.tests {
        requires com.example.orders;
        requires org.junit.jupiter.api;
        opens com.example.orders.contract.tests
            to org.junit.platform.commons;
    }

Test chỉ import package API đã export. Điều này cho phép bộ test hoạt động như một **client độc lập** và xác minh ranh giới module.

Tên module và nhu cầu mở package cho JUnit tùy phiên bản JUnit/test launcher đang dùng; `org.junit.platform.commons` là ví dụ cho một thành phần có thể tham gia reflection. Hãy căn cứ vào thông báo `InaccessibleObjectException` hoặc cấu hình launcher thực tế để xác định target.

Test module riêng thường phù hợp với contract tests hoặc integration tests. Nó không cần trở thành một phần của artifact production.

## 6. Khi test cần truy cập package-private: dùng test patch phù hợp

Có những unit test được thiết kế để thử một thuật toán package-private bên trong module thay vì chỉ qua API công khai.

Ví dụ production có class:

    package com.example.orders.internal;

    final class OrderRules {
        static boolean validQuantity(int quantity) {
            return quantity > 0;
        }
    }

Test nằm trong cùng package:

    package com.example.orders.internal;

    import org.junit.jupiter.api.Test;

    import static org.junit.jupiter.api.Assertions.assertFalse;
    import static org.junit.jupiter.api.Assertions.assertTrue;

    class OrderRulesTest {
        @Test
        void validatesQuantity() {
            assertTrue(OrderRules.validQuantity(3));
            assertFalse(OrderRules.validQuantity(0));
        }
    }

Chỉ đặt test class ở cùng tên package trong một JAR khác **chưa chắc** giúp truy cập package-private. Với JPMS, hai class cùng package name nhưng khác runtime module hoặc class loader không nhất thiết thuộc cùng runtime package.

Cơ chế `--patch-module` cho phép bổ sung compiled test classes vào named module trong môi trường kiểm thử:

    --patch-module com.example.orders=build/test-classes

Khi được patch đúng cách, test class có thể được xem là một phần của module `com.example.orders`. Tuy nhiên, nếu test code dùng JUnit API nằm trong module khác hoặc trên classpath, module production được patch có thể còn cần quan hệ readability phù hợp.

Điểm quan trọng: `--patch-module` là lựa chọn cho **test JVM/compile task**, không phải lý do đóng gói test class vào production JAR.

## 7. --patch-module không tự giải quyết mọi quyền truy cập

Phải phân biệt vấn đề mà từng tùy chọn giải quyết:

    --patch-module
    --add-reads
    --add-exports
    --add-opens

| Tùy chọn | Vai trò |
|---|---|
| `--patch-module X=path` | Bổ sung hoặc thay nội dung class/resource vào module X trong môi trường được cấu hình |
| `--add-reads X=Y` | Bổ sung quan hệ module X đọc Y |
| `--add-exports X/p=Y` | Cho Y truy cập kiểu public trong package p của X |
| `--add-opens X/p=Y` | Mở package p của X cho Y thực hiện deep reflection |

Ví dụ, test classes được patch vào `com.example.orders` nhưng JUnit API nằm trên classpath. Để test code đọc các kiểu JUnit trong unnamed module, cấu hình compile/test có thể cần:

    --add-reads=com.example.orders=ALL-UNNAMED

Nếu framework test trên classpath còn cần dùng reflection với các test method không public trong package `com.example.orders.internal`, JVM test có thể cần:

    --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED

Những flag này chỉ có ý nghĩa nếu JUnit thực sự nằm trong unnamed module. Nếu framework ở named module, target phải là module name thực tế của framework.

Không sao chép toàn bộ flags vào production launcher. Cấu hình compile tests và chạy tests cũng có thể khác nhau nên cần đặt flag ở đúng giai đoạn.

## 8. Khi cần deep reflection, mở đúng một package trong JVM test

Giả sử framework sử dụng reflection để đọc field private của class nội bộ:

    package com.example.orders.internal;

    public final class OrderState {
        private String status = "NEW";
    }

Một test/framework thực hiện:

    Field field = OrderState.class.getDeclaredField("status");
    field.setAccessible(true);

Với named module, nếu package chưa được mở cho caller, `setAccessible(true)` có thể ném:

    java.lang.reflect.InaccessibleObjectException

Nếu framework chạy trên classpath trong JVM test, có thể cấu hình:

    --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED

Nếu framework chạy trong named module `com.example.test.framework`, dùng:

    --add-opens=com.example.orders/com.example.orders.internal=com.example.test.framework

Điều này chỉ mở **một package** của **một source module** cho **đúng target**. Không ảnh hưởng đến các package khác trong module production.

Có thể dùng `trySetAccessible()` để kiểm tra khả năng bật quyền mà không dựa vào exception cho trường hợp bị chặn bởi module access:

    if (field.trySetAccessible()) {
        Object value = field.get(state);
        System.out.println(value);
    } else {
        System.out.println("Reflection không được phép");
    }

Nếu chỉ cần gọi method public, hãy kiểm tra `requires` và `exports`, không sử dụng `--add-opens` như một cách sửa chung cho mọi lỗi truy cập.

## 9. Đặt flags đúng nơi: JVM test không phải JVM production

Một dự án có thể dùng nhiều JVM:

- JVM của ứng dụng production.
- JVM chạy unit tests.
- JVM chạy integration tests.
- JVM của IDE test runner.
- JVM do Maven Surefire/Failsafe hoặc Gradle Test tạo.
- JVM thực thi một công cụ build khác.

Khi một test cần `--add-opens`, flag phải được truyền cho **JVM thực sự chạy test framework**. Đặt vào command khởi chạy production không tự làm JVM kiểm thử nhận được flag.

Với Maven Surefire, một cấu hình minh họa:

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>
          --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED
        </argLine>
      </configuration>
    </plugin>

Nếu dùng JaCoCo hoặc hệ thống khác đã đặt `argLine`, phải hợp nhất các argument thay vì ghi đè cấu hình cũ. `ALL-UNNAMED` chỉ đúng khi code reflection của test framework chạy trong unnamed module.

Với Gradle Java plugin:

    tasks.withType(Test).configureEach {
        jvmArgs(
            '--add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED'
        )
    }

Tùy source set và Gradle/JUnit configuration, có thể cần lựa chọn module target khác. Cấu hình nên phản ánh JUnit thực tế đang được nạp từ classpath hay module path.

## 10. Dùng module-info production để mô tả nhu cầu production

Nếu một framework thực sự cần reflection **khi ứng dụng chạy trong production**, việc mở package trong descriptor có thể là thiết kế đúng.

Ví dụ:

    module com.example.orders {
        exports com.example.orders.api;

        opens com.example.orders.persistence
            to com.example.orm;
    }

Module đang chứa các entity cần ORM mapping có thể chủ động mở package persistence cho module ORM. Đây là hợp đồng production có chủ đích.

Ngược lại, một package `com.example.orders.internal` chỉ cần mở cho JUnit trong test không nên được thêm vào descriptor production:

    opens com.example.orders.internal;

chỉ vì test sẽ ngắn hơn.

Một cách phân biệt: **Nếu xóa toàn bộ test khỏi dự án, production có còn cần quyền reflection đó không?** Nếu không, hãy cân nhắc đặt quyền trong cấu hình test thay vì module descriptor production.

Qualified opens trong descriptor vẫn là quyền tồn tại ở production artifact; nó không tự trở thành test-only vì module nhận quyền có tên chứa `test`.

## 11. Đừng export internals chỉ để test import dễ dàng

Một cách né ranh giới test khác là thêm:

    exports com.example.orders.internal;

Điều này làm package internal được công bố như API có thể truy cập từ các module khác, miễn là đáp ứng readability và Java access modifiers.

Việc export quá rộng có thể tạo phụ thuộc lâu dài: module khác có thể bắt đầu sử dụng class internal. Khi refactor cấu trúc dữ liệu, thay đổi package hoặc xóa class sẽ phá vỡ code phụ thuộc vào phần vốn không được thiết kế là public API.

Các lựa chọn tốt hơn gồm:

- Test behavior qua package API đã export.
- Test package-private implementation bằng `--patch-module` trong môi trường test.
- Mở có giới hạn cho reflection của test framework bằng VM options test.
- Tách thuật toán thực sự cần tái sử dụng thành API/package được thiết kế công khai.
- Trích một package test-support riêng nếu dự án có lý do kiến trúc rõ ràng.

Không nên tạo một `export` production chỉ vì test runner chưa được cấu hình đúng.

## 12. JUnit và test discovery: tìm test khác với được phép gọi test

JUnit Platform có nhiệm vụ phát hiện và chạy test. Quá trình discovery có thể nhìn thấy một test class, nhưng reflection gọi constructor hoặc test method không public vẫn phải tuân theo JPMS.

Ví dụ lỗi có thể cho biết:

    module com.example.orders does not "opens
    com.example.orders.internal" to module org.junit.platform.commons

Trong tình huống này, target cần quyền là module phản chiếu thực sự, ví dụ `org.junit.platform.commons`, không nhất thiết là module chính chứa ứng dụng.

Cấu hình hướng mục tiêu:

    --add-opens=com.example.orders/com.example.orders.internal=org.junit.platform.commons

Chỉ xem đây là ví dụ: tên module target trong dự án phải lấy từ stack trace, thông báo lỗi và cách JUnit được nạp. Một setup khác có thể sử dụng unnamed module hoặc thành phần JUnit khác.

Khi test runner không phát hiện bài test, nguyên nhân cũng có thể là source set, test engine hoặc module path, chứ không phải thiếu `opens`. Không thêm flag reflection trước khi xác định đúng giai đoạn lỗi.

## 13. Kiểm tra trạng thái mở package bằng Module API

Có thể truy vấn package có đang mở cho một module khác tại runtime hay không:

    Module source = OrderService.class.getModule();
    Module target = MyTestFramework.class.getModule();

    boolean openForTarget = source.isOpen(
        "com.example.orders.internal",
        target
    );

    System.out.println(openForTarget);

Khi chạy với đúng VM options, kết quả có thể là `true`. Nếu package chưa mở cho target thực sự, kết quả có thể là `false`.

Lưu ý khác biệt:

    source.isExported("com.example.orders.api", target);
    source.isOpen("com.example.orders.internal", target);

Phép kiểm tra đầu tiên liên quan truy cập API public; phép kiểm tra thứ hai liên quan deep reflection.

API này hữu ích khi chẩn đoán môi trường test/module layer, nhưng không nên dùng kết quả `isOpen` như lý do tự động mở thêm package production. Cấu hình quyền vẫn cần có phạm vi và mục đích rõ ràng.

## 14. Maven và Gradle: tách test-scoped workaround

Trong Maven, cấu hình compiler plugin, Surefire/Failsafe và runtime launcher có thể khác nhau. Các đường cấu hình cần kiểm tra riêng:

- Compile module production: compiler module path và descriptor.
- Compile test: classpath/module path test, cơ chế patch nếu dùng.
- Chạy unit test: Surefire/JUnit VM options.
- Chạy integration test: Failsafe hoặc runner chuyên biệt.
- Chạy production: launcher không chứa test-only overrides.

Với Gradle, `JavaCompile` và `Test` là các task khác nhau. Cấu hình `test` và `integrationTest` (nếu tự định nghĩa) có thể không giống nhau. Một flag thêm vào `test.jvmArgs` không tự áp dụng cho mọi JVM hoặc task tùy biến.

Một quy tắc cấu hình dễ bảo trì là dùng một hàm hoặc convention chung cho các **test tasks thực sự cần reflection**, thay vì thêm mọi flag vào `JAVA_TOOL_OPTIONS` toàn hệ thống.

Nếu dự án cung cấp hai đường build classpath và module path trong giai đoạn migration, cần đảm bảo test phản ánh đúng cấu hình production mục tiêu. Test chạy được ở classpath chưa chứng minh ranh giới JPMS production đúng.

## 15. Kiểm thử module boundary như một hợp đồng

Ngoài unit tests, nên có một tập test bảo đảm ranh giới module được giữ.

Ví dụ các điều kiện cần xác nhận:

1. Module `com.example.orders` export đúng package `com.example.orders.api`.
2. Các package `internal` và `persistence` không bị export rộng khi không cần.
3. Các package không cần production reflection không bị mở trong descriptor.
4. Module client chỉ dùng API công khai vẫn chạy tốt trên module path.
5. Test-specific flags không xuất hiện trong lệnh khởi chạy production.
6. Provider modules và service discovery (nếu có) được resolve đúng mà không đòi mở cả module.

Có thể quan sát descriptor của modular JAR:

    jar --describe-module --file orders.jar

Với chương trình Java, đọc descriptor:

    ModuleDescriptor descriptor =
        OrderService.class.getModule().getDescriptor();

    System.out.println(descriptor.exports());
    System.out.println(descriptor.opens());

Đây là ví dụ về kiểm thử kiến trúc ở giai đoạn sau. Bản thân việc soạn một module có descriptor nhỏ, rõ ràng giúp các phép kiểm tra boundary có ý nghĩa.

## 16. Quy trình quyết định khi một test bị lỗi access

Khi gặp `IllegalAccessException`, `InaccessibleObjectException` hoặc lỗi package visibility, có thể làm theo thứ tự:

**Bước 1 — Xác định lỗi.**

- Nếu `package ... is not visible` lúc compile: xem `requires`, readability, `exports`.
- Nếu `InaccessibleObjectException` lúc `setAccessible(true)`: xem `opens` cho module caller.
- Nếu `IllegalAccessException` khi invoke/field access bằng reflection: xem access modifier, loại reflection và module access.
- Nếu `module not found`: sửa module path trước, không mở package tùy ý.

**Bước 2 — Xác định phạm vi bài test.**

Test đang kiểm tra public API, package-private implementation, hay hành vi framework reflection?

**Bước 3 — Chọn giải pháp hẹp nhất.**

- Public API test: dùng exports đã được thiết kế.
- Test cùng module/package: xem `--patch-module`.
- Framework cần private reflection trong test: `--add-opens` đúng package và target.
- Production framework thật sự cần reflection: thiết kế `opens` có giới hạn theo nhu cầu production.

**Bước 4 — Đặt quyền ở đúng nơi.**

Dùng test compile/runtime flags khi chỉ test cần; không ghi thay đổi rộng vào production descriptor.

**Bước 5 — Chạy lại trong môi trường mục tiêu.**

Đảm bảo test runtime thực sự nhận flags; đọc thông báo tiếp theo nếu còn lỗi khác. Không suy ra mọi lỗi đều cùng một nguyên nhân.

## 17. So sánh các cách tiếp cận

| Lựa chọn | Đóng gói production | Hỗ trợ test | Khi nào phù hợp |
|---|---|---|---|
| Test qua public API | Giữ nguyên | Tốt cho hành vi công khai | Mặc định ưu tiên |
| Test module riêng | Giữ ranh giới API | Tốt cho contract/integration | Muốn kiểm tra client bên ngoài |
| `--patch-module` trong test | Không sửa descriptor production | Có thể test package-private | Unit tests cần ở cùng module/package |
| Test-scoped `--add-opens` | Không sửa artifact production | Cho phép deep reflection theo package/target | JUnit, mock/serialization framework cần reflection |
| `opens p to m` trong descriptor | Mở một package khi production chạy | Có thể hỗ trợ test | Có nhu cầu reflection production thực sự |
| `open module` | Mở tất cả package | Có thể làm test dễ chạy | Chỉ khi toàn module được chủ ý thiết kế cho reflection rộng |

Chọn giải pháp dựa trên hợp đồng public của module và rủi ro reflection thực tế, không dựa duy nhất vào việc cách nào giúp bỏ qua lỗi nhanh nhất.

## 18. Những nhầm lẫn thường gặp

- **Tưởng `open module` chỉ mở package cho JUnit.** Nó mở mọi package của module cho deep reflection ở runtime.
- **Tưởng package được `exports` đã cho phép đọc field private.** Deep reflection cần quyền mở package thích hợp.
- **Tưởng test nằm trong cùng tên package là đủ để gọi package-private code.** Cần xét runtime module và class loader; `--patch-module` có thể phù hợp.
- **Tưởng `--patch-module` tự thêm readability tới test framework.** Có thể cần `--add-reads` khi test module được patch và framework nằm ngoài module đó.
- **Tưởng `ALL-UNNAMED` có nghĩa tất cả named modules.** Nó chỉ áp dụng cho unnamed modules.
- **Tưởng dùng `--add-opens` là sửa lỗi thiếu dependency.** Nó không tạo class, JAR hoặc module còn thiếu.
- **Tưởng thay module descriptor production là cách duy nhất để test chạy.** Test runner và VM options có thể cấp quyền trong phạm vi test.
- **Tưởng test pass trên classpath chứng minh module path production cũng đúng.** Đây là hai cơ chế tổ chức và kiểm soát truy cập khác nhau.
- **Tưởng mọi quyền test nên chuyển thành quyền production.** Test có đặc quyền dành riêng cho việc quan sát nội bộ; production không nhất thiết cần chúng.

## Ghi nhớ

- Đừng đổi production module thành `open module` chỉ để tiện viết test.
- Mặc định kiểm thử hành vi qua **API được export**.
- Nếu cần kiểm thử package-private implementation, cân nhắc **test-only `--patch-module`**.
- Nếu framework test cần deep reflection, dùng **`--add-opens` giới hạn đúng package và target** trên JVM test.
- Nếu một framework production thật sự cần reflection, mô tả quyền đó bằng `opens` phù hợp với thiết kế module.
- Phân biệt `exports` (public API), `opens` (reflection), `--add-reads` (readability) và `--patch-module` (test classes trong module).
- Giữ production artifact và lệnh production launcher không bị nhiễm các quyền chỉ phục vụ kiểm thử.

Một bộ test hữu ích phải giúp module trở nên đáng tin cậy **mà không làm ranh giới production yếu đi**. Kiểm soát quyền theo phạm vi test và theo đúng package/module sẽ giữ được cả khả năng kiểm thử lẫn lợi ích đóng gói của JPMS.