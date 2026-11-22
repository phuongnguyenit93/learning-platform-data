# Dùng --patch-module trong tình huống kiểm thử phù hợp

**--patch-module** là tùy chọn của Java Platform Module System (JPMS), cho phép bổ sung class hoặc resource vào một named module đã tồn tại trong lúc biên dịch hoặc chạy chương trình. Trong kiểm thử, tùy chọn này thường được dùng để đưa test class vào chính module đang được kiểm thử. Nhờ đó, test có thể kiểm tra package nội bộ và các thành viên có phạm vi package mà không phải công khai implementation chỉ để phục vụ test.

Tính năng này được giới thiệu cùng module system trong Java 9 và vẫn có trong các JDK hiện đại. Ví dụ trong bài dùng cú pháp Java 17 trở lên. **--patch-module** là công cụ phục vụ build, test và một số tình huống tích hợp có kiểm soát; nó không phải cách thông thường để sửa cấu trúc module của ứng dụng khi triển khai production.

## 1. Vấn đề khi kiểm thử named module

JPMS phân chia ứng dụng thành các named module. Một module khai báo tên, dependency và package được công bố trong **module-info.java**.

Ví dụ:

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

Package **com.example.billing.api** được công bố cho module khác sử dụng. Package **com.example.billing.internal** không được export nên module khác không thể import các kiểu trong package này như API thông thường.

Cách đóng gói này tốt cho kiến trúc production, nhưng tạo ra một câu hỏi khi kiểm thử: làm thế nào để test những quy tắc nội bộ mà không biến package implementation thành API công khai?

Giả sử module có class package-private:

~~~java
package com.example.billing.internal;

final class PricingPolicy {
    static int applyDiscount(int priceCents, int percent) {
        return priceCents - priceCents * percent / 100;
    }
}
~~~

Nếu test được biên dịch và chạy như một phần của unnamed module trên classpath, nó không tự động trở thành thành viên của **com.example.billing**. Nó không có cùng quyền truy cập package và bị ranh giới module giới hạn.

Có thể giải quyết việc này bằng cách patch test class vào named module đích. Khi đó, test class được nạp như một phần của module đang kiểm thử và có thể truy cập package nội bộ theo các quy tắc truy cập Java thông thường.

## 2. Cú pháp và cách hoạt động

Cú pháp cơ bản:

~~~text
--patch-module <module>=<path>
~~~

Trong đó:

- **module** là tên của named module cần được bổ sung class hoặc resource.
- **path** là một thư mục hoặc JAR chứa class/resource cần đưa vào module.
- Có thể chỉ định nhiều đường dẫn; dấu phân cách phụ thuộc hệ điều hành (**;** trên Windows, **:** trên Linux/macOS).

Có hai nơi thường dùng tùy chọn này:

| Nơi sử dụng | Mục đích |
|---|---|
| **javac --patch-module** | Cho compiler xem source/class được biên dịch như phần bổ sung của module đích |
| **java --patch-module** | Cho JVM nạp class/resource bổ sung như phần của module đích khi chạy |

Ví dụ:

~~~bash
javac --module-path mods --patch-module com.example.billing=tests -d test-out tests/com/example/billing/internal/PricingPolicyTest.java
java --module-path mods --patch-module com.example.billing=test-out -m com.example.billing/com.example.billing.internal.PricingPolicyTest
~~~

Trong lệnh biên dịch, thư mục **tests** là patch path để compiler xác định test thuộc module **com.example.billing**. Trong lệnh chạy, thư mục **test-out** chứa bytecode test và được patch vào cùng module.

**--patch-module** bổ sung hoặc thay thế class/resource theo thứ tự tìm kiếm của patch path. Patch path được tìm trước nội dung module gốc. Vì vậy, một class cùng tên trong patch path có thể che class cùng tên bên trong module. Hãy tránh trùng tên ngoài chủ đích kiểm thử thay thế implementation.

Module descriptor gốc vẫn giữ vai trò xác định tên module, dependency, **exports**, **opens**, **uses** và **provides**. Patch path không phải nơi thay thế **module-info.java** và không tạo ra một module mới.

## 3. Vì sao test được patch vào module có thể truy cập package nội bộ?

Khi test class được patch vào **com.example.billing**, JVM xem test class là một phần của named module đó. Nếu test và class cần kiểm tra cùng package, các quy tắc truy cập package-private của Java cho phép test gọi thành viên package-private.

Điều này hữu ích khi:

- Kiểm thử thuật toán nội bộ mà không muốn biến class implementation thành public.
- Kiểm tra class trong package không export.
- Kiểm thử tương tác giữa các class trong cùng module.
- Thay thế một class/resource của module bằng bản thử nghiệm có kiểm soát.
- Tích hợp test framework cần chạy test trong module đích.

**--patch-module** không xóa bỏ mọi quy tắc truy cập của Java. Ví dụ, một class khác package vẫn không thể gọi method package-private chỉ vì nó thuộc cùng module. Thành viên **private** vẫn tuân theo quyền truy cập cấp class; nếu dùng reflection để truy cập sâu, vẫn phải tuân theo các điều kiện của reflection và module.

Cũng cần phân biệt quyền truy cập nội bộ của test với quyền của module bên ngoài. Patch test vào module đích không có nghĩa package đó được export cho module khác.

## 4. Ví dụ hoàn chỉnh: test package-private class mà không export package nội bộ

Ví dụ tạo một module **com.example.app** chỉ có package nội bộ. Class **PricingPolicy** không public và method **applyDiscount** có phạm vi package. Test được biên dịch và chạy như một phần của module này.

Cấu trúc thư mục:

~~~text
project/
  src/
    com.example.app/
      module-info.java
      com/example/app/internal/PricingPolicy.java
  tests/
    com/example/app/internal/PricingPolicyTest.java
  mods/
  test-out/
~~~

**Tệp src/com.example.app/module-info.java:**

~~~java
module com.example.app {
}
~~~

Module không export package nào. Đây là chủ ý của ví dụ: implementation chỉ được sử dụng bên trong module.

**Tệp src/com.example.app/com/example/app/internal/PricingPolicy.java:**

~~~java
package com.example.app.internal;

final class PricingPolicy {
    static int applyDiscount(int priceCents, int percent) {
        if (priceCents < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Invalid discount input");
        }
        return priceCents - priceCents * percent / 100;
    }
}
~~~

Class và method đều không public. Chúng không tạo thành API cho module khác.

**Tệp tests/com/example/app/internal/PricingPolicyTest.java:**

~~~java
package com.example.app.internal;

public class PricingPolicyTest {
    public static void main(String[] args) {
        int discounted = PricingPolicy.applyDiscount(10000, 15);
        if (discounted != 8500) {
            throw new AssertionError("Expected 8500, got " + discounted);
        }
        System.out.println("Discounted price: " + discounted);
    }
}
~~~

Test nằm trong cùng package với class cần kiểm tra. Khi test được patch vào **com.example.app**, nó có thể gọi method package-private **applyDiscount**.

Biên dịch module production trước:

~~~bash
javac --release 17 -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/internal/PricingPolicy.java
~~~

Biên dịch test và khai báo patch path ở giai đoạn compile:

~~~bash
javac --release 17 --module-path mods --patch-module com.example.app=tests -d test-out tests/com/example/app/internal/PricingPolicyTest.java
~~~

Chạy test và patch thư mục bytecode test vào module:

~~~bash
java --module-path mods --patch-module com.example.app=test-out -m com.example.app/com.example.app.internal.PricingPolicyTest
~~~

Kết quả chính xác:

~~~text
Discounted price: 8500
~~~

Test đã gọi được method package-private mà không cần khai báo **exports com.example.app.internal**. Package nội bộ vẫn không được công bố cho module khác.

Nếu bỏ **--patch-module** ở bước biên dịch hoặc chạy, test không còn được xử lý như thành viên của module đích. Tùy cách tổ chức source và module path, compiler hoặc JVM có thể báo lỗi package không được export, package không thuộc module hoặc không tìm thấy class test.

## 5. Dùng patch-module để thay class/resource trong test

Ngoài việc đưa test class vào module, patch path còn có thể chứa một class thay thế class cùng tên trong module. JVM tìm class trong patch path trước nội dung module gốc.

Một tình huống có thể gặp là kiểm thử tích hợp với implementation thay thế:

~~~text
mods/
  com.example.billing/
    com/example/billing/internal/RemoteGateway.class
test-patch/
  com/example/billing/internal/RemoteGateway.class
~~~

Khi chạy:

~~~bash
java --module-path mods --patch-module com.example.billing=test-patch -m com.example.billing/com.example.billing.api.Main
~~~

JVM nạp **RemoteGateway.class** từ **test-patch** trước class cùng tên trong module gốc. Test có thể dùng fake gateway hoặc implementation kiểm thử để kiểm tra phần còn lại của module mà không gọi dịch vụ bên ngoài.

Cách thay class theo tên phải được quản lý cẩn thận:

- Class thay thế phải tương thích với các kiểu và chữ ký mà code gọi mong đợi.
- Patch path phải chứa đúng package và tên class.
- Test cần kiểm tra cả trường hợp patch được áp dụng và trường hợp chạy với module gốc.
- Không để patch path kiểm thử lọt vào artifact hoặc lệnh chạy production.
- Không dùng fake implementation để che giấu lỗi tích hợp thật; vẫn cần kiểm thử tích hợp với dependency thật ở môi trường phù hợp.

Nếu chỉ cần thay dependency trong test, dependency injection hoặc interface có thể là giải pháp dễ bảo trì hơn. Patch module hữu ích khi ranh giới module hoặc cấu trúc class cũ khiến cách thay thế thông thường không phù hợp.

## 6. Phân biệt --patch-module với các tùy chọn module khác

Các tùy chọn JPMS thường xuất hiện cùng nhau nhưng giải quyết các vấn đề khác nhau.

| Tùy chọn | Tác dụng | Khi nào cân nhắc |
|---|---|---|
| **--patch-module** | Bổ sung hoặc thay class/resource trong một module | Đưa test vào module đích hoặc thay implementation/resource có kiểm soát |
| **--add-reads** | Thêm quan hệ đọc module tại runtime/compile theo công cụ | Module cần đọc một module khác nhưng descriptor chưa khai báo |
| **--add-exports** | Export package cho module đích | Cần truy cập kiểu public trong package chưa được export |
| **--add-opens** | Mở package cho deep reflection | Framework cần truy cập field/constructor/method không public bằng reflection |
| **--module-path** | Chỉ định nơi tìm named module | Cấu hình đường dẫn module khi biên dịch hoặc chạy |

Không chọn **--add-exports** hoặc **--add-opens** chỉ vì test không truy cập được package-private class. Nếu mục tiêu là đưa test vào chính module để kiểm tra package nội bộ, **--patch-module** mô tả đúng ý định hơn.

Ngược lại, nếu test chạy trong một module riêng và cần kiểm tra package bằng reflection, patch test vào module đích có thể không phải kiến trúc mong muốn. Khi đó, cân nhắc **opens** hoặc **--add-opens** cho đúng module nhận quyền. Nếu cần biên dịch và import API public, dùng **exports** hoặc **--add-exports**.

## 7. Giới hạn và rủi ro khi dùng

**--patch-module** là công cụ mạnh vì nó thay đổi tập class/resource mà module nhìn thấy trong một lần chạy. Dùng không đúng có thể làm kết quả test khác với ứng dụng production.

Các giới hạn cần nhớ:

1. **Không sửa module descriptor:** patch path không thay đổi **module-info.class**, tên module, dependency hoặc directive của module.
2. **Không tự tạo quyền deep reflection:** patch class vào module không biến private member thành public. Quy tắc reflection vẫn áp dụng.
3. **Không thay thế module path:** patch path bổ sung nội dung cho một module đã tồn tại; nó không thay thế việc resolve module đích.
4. **Có thể che class gốc:** class cùng tên trong patch path được ưu tiên. Một bản thay thế sai chữ ký có thể gây lỗi linkage hoặc hành vi khác.
5. **Không phù hợp để cấu hình production tùy tiện:** patch runtime có thể làm artifact chạy khác nội dung đã build và khó tái hiện lỗi.
6. **Cẩn trọng với package của JDK:** patch các module nền tảng như **java.base** chỉ nên dành cho phát triển JDK hoặc thử nghiệm đặc biệt có kiểm soát. Ứng dụng thông thường nên dùng API được hỗ trợ.
7. **Không nhầm quyền module với quyền Java:** cùng module không đồng nghĩa mọi class có thể truy cập private member của nhau.
8. **Build tool phải truyền option tới đúng tiến trình:** test runner có thể fork JVM riêng. Cần cấu hình patch option cho cả compiler và test JVM khi cần.

## 8. Tích hợp với build và test framework

Trong dự án Maven hoặc Gradle, không nên tự ghép lệnh shell thủ công trong mọi lần build. Hãy cấu hình test framework hoặc plugin để:

- Biên dịch production module vào output riêng.
- Biên dịch test source với **--patch-module** trỏ tới module cần kiểm thử.
- Chạy test JVM với **--patch-module** trỏ tới thư mục chứa test class.
- Giữ module path và patch path nhất quán giữa compile và runtime.
- Chỉ bật cấu hình này trong task/test profile.
- Kiểm tra lệnh cuối cùng mà plugin truyền cho **javac** và JVM, đặc biệt khi test runner fork process.

Một số test framework hoặc build plugin có hỗ trợ module path và patch module riêng. Cấu hình cụ thể phụ thuộc phiên bản Maven/Gradle, plugin compiler, test runner và cách tổ chức module. Hãy dùng tài liệu của đúng phiên bản plugin trong dự án; không sao chép cấu hình từ một bản plugin khác mà chưa kiểm tra.

Nếu dự án dùng JUnit, test class có thể được patch vào module rồi được JUnit engine phát hiện theo cấu hình test runner. Việc patch module không tự khởi chạy JUnit và cũng không thay thế dependency của JUnit; nó chỉ quyết định test class thuộc module nào khi được biên dịch/nạp.

## 9. Quy trình lựa chọn trong thực tế

Trước khi thêm **--patch-module**, hãy trả lời lần lượt:

1. Test cần kiểm tra hành vi công khai hay chi tiết package-private?
2. Package nội bộ có thực sự cần được kiểm tra trực tiếp, hay test qua API public là đủ?
3. Test cần là thành viên của named module đích hay cần chạy như một module riêng?
4. Nếu test cần truy cập package-private, có thể đặt test cùng package và patch vào module không?
5. Test có cần thay một class/resource cụ thể để mô phỏng dependency không?
6. Cấu hình patch được giới hạn trong test task và không lọt vào lệnh chạy production chưa?
7. Có kiểm thử cả trường hợp dùng class/resource gốc và trường hợp patch chưa?
8. Sau khi nâng JDK hoặc build plugin, compile command và test JVM command có còn đúng không?

Ưu tiên kiểm thử qua API công khai để test ít phụ thuộc implementation. Dùng **--patch-module** khi cần kiểm tra chi tiết bên trong module và có lý do rõ ràng để đặt test vào cùng module. Nếu dùng thường xuyên, hãy ghi lại module đích, patch path, mục tiêu và nơi cấu hình để người bảo trì hiểu vì sao tùy chọn tồn tại.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo package không được export | Test đang được biên dịch như module ngoài, không phải phần của module đích | Dùng **javac --patch-module** với đúng tên module và patch path |
| Runtime không tìm thấy class test | Chỉ patch ở bước compile hoặc patch sai thư mục bytecode lúc chạy | Truyền **--patch-module** cho JVM và trỏ tới test output |
| Test không gọi được method package-private | Test không nằm cùng package hoặc không được patch vào đúng module | Kiểm tra package khai báo và tên module trong option |
| Class gốc vẫn được nạp | Patch path sai cấu trúc thư mục, sai module hoặc không chứa class đúng tên | Kiểm tra đường dẫn package, tên class và patch path |
| Runtime lỗi **NoSuchMethodError** hoặc **LinkageError** | Class thay thế không tương thích với chữ ký mà module mong đợi | Đồng bộ API/chữ ký hoặc chỉ patch đúng resource cần thay |
| Test chạy được nhưng production cũng dùng fake | Patch option bị đưa vào cấu hình chạy production | Giới hạn patch trong task/profile kiểm thử và kiểm tra lệnh JVM production |
| Đã patch nhưng vẫn không đọc được private field | Patch module không bỏ qua quy tắc truy cập private/reflection | Dùng API phù hợp hoặc mở package có kiểm soát nếu thực sự cần deep reflection |
| Dùng **--patch-module** thay cho **--add-opens** | Nhầm việc thêm class vào module với việc cấp quyền reflection cho module khác | Chọn option theo mục tiêu: patch class/resource hay mở package |

## 11. Checklist trước khi sử dụng

- [ ] Module đích là named module đã được resolve.
- [ ] Patch path chứa đúng class/resource cần bổ sung hoặc thay thế.
- [ ] Test source được biên dịch với **javac --patch-module** khi cần cùng module.
- [ ] Test bytecode được patch vào module đích khi chạy.
- [ ] Test package-private nằm trong đúng package.
- [ ] Không giả định **--patch-module** tự mở private member hoặc export package.
- [ ] Không patch module descriptor hoặc dựa vào patch để thay đổi dependency.
- [ ] Patch chỉ áp dụng cho test/build task cần thiết.
- [ ] Test chạy với module gốc và patch path đúng như dự kiến.
- [ ] Build log hoặc command line có thể truy vết option và patch path.

## 12. Tài liệu tham khảo

- [Java SE 25 — javac command: --patch-module](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Java SE 25 — java command: --patch-module](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Java SE API — Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html)
