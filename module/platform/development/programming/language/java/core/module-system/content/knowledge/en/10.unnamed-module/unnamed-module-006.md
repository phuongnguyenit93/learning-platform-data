# Migration khi code test vẫn ở unnamed module

Khi chuyển một ứng dụng Java từ classpath sang Java Platform Module System (JPMS), không nhất thiết phải chuyển toàn bộ mã test thành named module ngay lập tức. Một cách migration phổ biến là giữ test source và test framework trên classpath, trong khi module production đã có `module-info.java` và được chạy trên module path.

Trong cấu hình này, các lớp test thuộc **unnamed module** của class loader. Unnamed module có thể đọc các named module đã được phân giải, nhưng quyền truy cập vẫn chịu sự chi phối của ranh giới JPMS: test có thể sử dụng public API trong package được export; package nội bộ chưa export vẫn bị đóng đối với truy cập mã nguồn thông thường.

Để migration diễn ra có kiểm soát, cần hiểu cách kết hợp `--module-path`, `--add-modules`, `--add-exports` và `--add-opens`, đồng thời phân biệt kiểm thử API công khai với kiểm thử nội bộ cần quyền truy cập đặc biệt.

## 1. Unnamed module trong bối cảnh test

Khi một lớp được nạp từ classpath, nó thuộc unnamed module gắn với class loader tương ứng. Khác với named module, unnamed module không có một `module-info.java` để khai báo `requires`, `exports` hoặc `opens`.

Ví dụ dự án:

```text
application/
├── src/main/java/
│   └── com.example.application/
│       ├── module-info.java
│       └── com/example/application/
│           ├── api/
│           │   └── OrderService.java
│           └── internal/
│               └── OrderRepository.java
└── src/test/java/
    └── com/example/application/
        └── OrderServiceTest.java
```

Mã production thuộc named module `com.example.application`. Nếu test được biên dịch và chạy từ classpath, `OrderServiceTest` thuộc unnamed module, dù nó dùng cùng tên package trong source code.

Đây là một ranh giới quan trọng: cùng viết `package com.example.application;` không làm cho test trên classpath trở thành một phần của named module production. Test và production vẫn ở hai module khác nhau.

## 2. Unnamed module có thể đọc named module

Unnamed module có khả năng đọc các named module đã được phân giải trong cấu hình runtime. Vì vậy, test trên classpath có thể tham chiếu các public type trong package mà named module export.

Descriptor production:

```java
module com.example.application {
    exports com.example.application.api;
}
```

Test source:

```java
package com.example.application;

import com.example.application.api.OrderService;

class OrderServiceTest {
    void createsOrder() {
        OrderService service = new OrderService();
        // Thực hiện kiểm tra hành vi public của service.
    }
}
```

Test có thể import và sử dụng `OrderService` nếu package API được export, module production có mặt trên module path và đã được phân giải.

Trong trường hợp này, test không cần một `module-info.java` riêng. Việc test nằm trong unnamed module không ngăn nó gọi public API được export.

## 3. Vì sao cần --module-path và --add-modules?

Khi biên dịch hoặc chạy test từ classpath, các named module production cần được đặt trên module path. Ngoài ra, module được test phải được đưa vào tập module được phân giải.

Ví dụ biên dịch test bằng `javac`:

```shell
javac ^
  --module-path build/mods ^
  --add-modules com.example.application ^
  --class-path lib/junit-platform-console-standalone.jar ^
  -d build/test-classes ^
  @build/test-sources.txt
```

Trên Windows PowerShell hoặc CMD, dấu `^` trong ví dụ là ký tự nối dòng của CMD; nếu chạy trong PowerShell, có thể viết lệnh trên một dòng hoặc dùng backtick để nối dòng. Trên Linux/macOS, có thể viết:

```shell
javac \
  --module-path build/mods \
  --add-modules com.example.application \
  --class-path lib/junit-platform-console-standalone.jar \
  -d build/test-classes \
  @build/test-sources.txt
```

Ý nghĩa các tùy chọn:

- `--module-path build/mods` cung cấp các named module đã biên dịch.
- `--add-modules com.example.application` yêu cầu đưa module production vào tập module được phân giải.
- `--class-path` cung cấp thư viện test như JUnit Platform Console Standalone.
- `-d build/test-classes` xác định thư mục chứa class test đã biên dịch.

Khi chạy test bằng JUnit Console Launcher:

```shell
java \
  --module-path build/mods \
  --add-modules com.example.application \
  --class-path "build/test-classes:lib/junit-platform-console-standalone.jar" \
  org.junit.platform.console.ConsoleLauncher execute \
  --scan-class-path
```

Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy (`;`); trên Linux và macOS là dấu hai chấm (`:`). Thay đường dẫn thư mục và tên module theo cấu trúc build thực tế.

`--add-modules` đặc biệt hữu ích vì test đang ở unnamed module. Test có thể đọc các named module đã được phân giải, nhưng module production vẫn cần hiện diện trong configuration runtime để lớp của nó được tìm thấy.

## 4. Kiểm thử public API: trường hợp nên ưu tiên

Nếu test chỉ kiểm tra hợp đồng công khai của module, cách migration đơn giản nhất là export đúng package API và giữ test trên classpath.

Ví dụ production:

```java
module com.example.application {
    exports com.example.application.api;
}
```

Test:

```java
import com.example.application.api.OrderService;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {
    @Test
    void calculatesOrderTotal() {
        OrderService service = new OrderService();

        assertEquals(120, service.totalFor("ORDER-01"));
    }
}
```

Test gọi các phương thức public như một client thông thường. Đây cũng là một lợi ích về thiết kế: test kiểm tra hành vi mà người dùng module có thể dựa vào, không cần biết cách module lưu dữ liệu hoặc tổ chức class nội bộ.

Không nên export package nội bộ chỉ để test có thể truy cập dễ hơn. Export là một phần của hợp đồng module; khi export package, module khác có thể phụ thuộc vào public type trong package đó.

## 5. Khi test cần truy cập public type trong package chưa export

Trong một số giai đoạn migration, test có thể cần truy cập một public class ở package nội bộ. Có thể tạm thời cấp quyền export bằng tùy chọn `--add-exports`.

Ví dụ module production:

```java
module com.example.application {
    exports com.example.application.api;
}
```

Test muốn tham chiếu một public class trong package:

```text
com.example.application.internal
```

Có thể thêm:

```shell
--add-exports com.example.application/com.example.application.internal=ALL-UNNAMED
```

Cần áp dụng tùy chọn ở cả giai đoạn biên dịch test và runtime nếu test tham chiếu package đó:

```shell
javac --module-path build/mods ^
      --add-modules com.example.application ^
      --add-exports com.example.application/com.example.application.internal=ALL-UNNAMED ^
      --class-path lib/junit-platform-console-standalone.jar ^
      -d build/test-classes @build/test-sources.txt
```

Khi chạy:

```shell
java --module-path build/mods ^
     --add-modules com.example.application ^
     --add-exports com.example.application/com.example.application.internal=ALL-UNNAMED ^
     --class-path "build/test-classes;lib/junit-platform-console-standalone.jar" ^
     org.junit.platform.console.ConsoleLauncher execute --scan-class-path
```

Cú pháp có dạng:

```text
--add-exports <module>/<package>=<target-module>
```

Ở đây:

- `com.example.application` là module sở hữu package.
- `com.example.application.internal` là package được export bổ sung.
- `ALL-UNNAMED` đại diện cho các unnamed module.

Tùy chọn này là một ngoại lệ ở cấp dòng lệnh, không sửa `module-info.java` trong JAR. Nên giới hạn nó vào test task và chỉ dùng cho package thật sự cần kiểm tra. Nếu package nội bộ thường xuyên phải được sử dụng, cần xem lại ranh giới API thay vì duy trì export bổ sung vô thời hạn.

## 6. --add-exports không cấp quyền deep reflection

`--add-exports` cho phép truy cập API Java thông thường vào package được chỉ định. Nó không tự cấp quyền cho framework dùng reflection sâu để đọc hoặc thay đổi private field, private method hay constructor không public.

Nếu test hoặc framework cần deep reflection, có thể dùng `--add-opens`:

```shell
--add-opens com.example.application/com.example.application.internal=ALL-UNNAMED
```

Ví dụ test dùng reflection:

```java
Field field = OrderRepository.class.getDeclaredField("connection");
boolean accessible = field.trySetAccessible();

assertTrue(accessible);
```

Để thao tác trên thành viên private được chấp nhận, module chứa package cần mở package đó cho module thực hiện reflection.

Cần nhớ:

- `--add-exports` phục vụ truy cập kiểu public từ package chưa export.
- `--add-opens` phục vụ deep reflection tại runtime.
- `--add-opens` không thay thế `--add-exports` khi mã test cần import một public type từ package chưa export.
- `--add-opens` là tùy chọn runtime, không phải giải pháp để biên dịch mã nguồn tham chiếu package chưa export.

Nếu framework test thực hiện reflection, đích mở phải là module thực sự chứa mã reflection. Khi JUnit hoặc thư viện hỗ trợ chạy trên classpath, đích thường là `ALL-UNNAMED`. Nếu framework được chạy như named module, cần dùng tên module của framework thay vì mặc định ALL-UNNAMED.

## 7. Test cùng package name vẫn không truy cập được package-private

Một nhầm lẫn phổ biến là đặt test trong cùng package với production rồi kỳ vọng truy cập được package-private member.

Ví dụ production:

```java
package com.example.application.internal;

class OrderRepository {
    void clearCache() {
    }
}
```

Test cũng khai báo:

```java
package com.example.application.internal;

class OrderRepositoryTest {
    void testClearCache() {
        OrderRepository repository = new OrderRepository();
        repository.clearCache();
    }
}
```

Nếu production thuộc named module còn test thuộc unnamed module, cùng tên package không khiến test trở thành thành viên của module production. Package-private access vẫn bị giới hạn theo ranh giới runtime package/module; test không thể dựa vào việc trùng tên package để truy cập class hoặc member package-private.

Thêm `--add-exports` cũng không biến package-private thành public. Nó chỉ mở quyền truy cập package ở cấp module cho các kiểu và thành viên vốn đã được phép truy cập theo access modifier Java.

Có ba hướng xử lý:

1. Kiểm tra hành vi qua public API nếu đó là hợp đồng cần bảo vệ.
2. Chuyển test white-box vào module đang kiểm thử, ví dụ cấu hình `--patch-module` hoặc dùng cơ chế test module path do build tool hỗ trợ.
3. Tái cấu trúc code để phần cần kiểm tra có một abstraction hoặc seam phù hợp, thay vì buộc test phụ thuộc vào chi tiết nội bộ.

Khi dùng `--patch-module`, test được đưa vào module đích trong quá trình biên dịch hoặc chạy. Cách này có thể cho phép test nằm trong cùng module boundary với mã production, nhưng cần cấu hình đồng bộ cả compile và runtime; các dependency test như JUnit cũng cần được module test đọc phù hợp. Không nên thêm `--patch-module` tùy tiện nếu chỉ cần kiểm tra public API.

## 8. Phân biệt --add-reads trong migration

`--add-reads` điều chỉnh quan hệ đọc giữa các module. Nó thường cần khi một named module cần đọc một module khác mà descriptor không khai báo, ví dụ trong một số cấu hình test hoặc tích hợp legacy.

Ví dụ:

```shell
--add-reads com.example.application=ALL-UNNAMED
```

Tùy chọn này nói rằng named module `com.example.application` được phép đọc unnamed module.

Trong kịch bản test thông thường, chiều truy cập là test ở unnamed module gọi API đã export của production named module. Unnamed module vốn có thể đọc các named module đã được phân giải, nên thường không cần `--add-reads` cho chiều truy cập này.

Không nên nhầm:

- `--add-reads` bổ sung quan hệ readability.
- `--add-exports` mở package cho truy cập mã Java thông thường.
- `--add-opens` mở package cho deep reflection.

Ba tùy chọn xử lý ba khía cạnh khác nhau. Chỉ thêm đúng tùy chọn mà lỗi hoặc nhu cầu thực tế yêu cầu.

## 9. Cấu hình test trong Gradle hoặc Maven

Khi dùng Gradle hoặc Maven, nguyên tắc vẫn giống lệnh JDK trực tiếp:

- Module production phải được biên dịch và đặt đúng trên module path.
- Test framework và test classes có thể vẫn nằm trên classpath.
- Module production phải được resolve trong runtime configuration.
- Các tùy chọn mở rộng quyền chỉ nên gắn với test task hoặc test JVM.

Trong Gradle, có thể cấu hình JVM arguments cho test task:

```groovy
tasks.test {
    jvmArgs(
        '--add-modules', 'com.example.application',
        '--add-opens',
        'com.example.application/com.example.application.internal=ALL-UNNAMED'
    )
}
```

Ví dụ này chỉ minh họa nơi đặt runtime arguments. Để module production thực sự nằm trên module path, build cần cấu hình modularity phù hợp, ví dụ bật suy luận module path khi dự án đáp ứng điều kiện của Gradle:

```groovy
java {
    modularity.inferModulePath = true
}
```

Nếu test source vẫn ở unnamed module, hãy xác minh cách Gradle tổ chức test compile classpath, test runtime classpath và module path trước khi thêm các flags. Không phải mọi dự án đều có cùng layout, đặc biệt khi dùng nhiều source set hoặc plugin test tùy chỉnh.

Với Maven, các tùy chọn JVM thường được truyền vào forked test JVM thông qua cấu hình Surefire/Failsafe. Cần kiểm tra phiên bản plugin và cách plugin tạo module path trong dự án cụ thể. Đừng sao chép một cấu hình module-path chung mà chưa xác nhận command line thực tế của test process.

## 10. Lộ trình migration thực tế

Một lộ trình thận trọng có thể chia thành các bước:

1. **Modularize production trước:** thêm `module-info.java` và khai báo dependency, package API.
2. **Giữ test trên classpath:** test tiếp tục thuộc unnamed module trong giai đoạn đầu.
3. **Resolve production module:** cấu hình module path và thêm module cần kiểm thử vào runtime configuration.
4. **Kiểm tra public API:** ưu tiên test qua package đã export.
5. **Chỉ mở package khi có lý do:** dùng `--add-exports` cho public type trong package chưa export và `--add-opens` cho deep reflection.
6. **Tách white-box test:** nếu cần package-private access, cân nhắc patch test vào module hoặc thiết kế lại điểm kiểm tra.
7. **Đưa flags về phạm vi test:** không để các tùy chọn mở rộng quyền vô tình trở thành cấu hình production.
8. **Đánh giá lại sau migration:** khi test đã ổn định, quyết định test có cần trở thành named module hoặc tiếp tục ở unnamed module.

Mục tiêu là giữ được tốc độ chuyển đổi nhưng vẫn nhìn thấy những điểm mà test đang phụ thuộc vào implementation nội bộ. Mỗi lần thêm `--add-exports` hoặc `--add-opens` nên có lý do cụ thể và có thể loại bỏ khi không còn cần thiết.

## Kết luận

Code test vẫn có thể nằm trong unnamed module trong khi production đã chuyển sang JPMS. Unnamed module có thể đọc named module đã được phân giải và sử dụng public API thuộc package được export. Với cấu hình phù hợp, test có thể tiếp tục chạy từ classpath trong giai đoạn migration.

Khi cần truy cập sâu hơn, hãy phân biệt đúng quyền: `--add-exports` cho public type trong package chưa export, `--add-opens` cho deep reflection, còn `--add-reads` điều chỉnh chiều readability. Các flags này không biến test trên classpath thành thành viên của named module và không cấp quyền package-private.

Nên bắt đầu bằng kiểm thử public API, giới hạn các ngoại lệ vào test runtime và chỉ dùng `--patch-module` hoặc chuyển test lên module path khi cần white-box testing. Như vậy production có thể giữ ranh giới module rõ ràng trong khi test suite được migration theo từng bước.