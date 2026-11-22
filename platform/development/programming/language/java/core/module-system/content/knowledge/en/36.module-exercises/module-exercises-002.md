# Ẩn implementation package và kiểm tra lỗi access

## 1. Mục tiêu của bài thực hành

Trong Java Platform Module System (JPMS), module có thể công khai một số package làm API và giữ các package triển khai ở bên trong. Bài thực hành này xây dựng một module thư viện có API công khai, một implementation package không export, sau đó kiểm tra các cách truy cập từ module tiêu thụ.

Mục tiêu gồm:

- Tạo một named module có package API và package implementation riêng.
- Chỉ export package API trong module descriptor.
- Thử truy cập public class nằm trong package implementation từ module khác.
- Phân biệt lỗi biên dịch, lỗi liên kết lúc chạy và lỗi deep reflection.
- Dùng các option JPMS trong môi trường thử nghiệm để hiểu tác động của exports và opens.
- Giữ implementation package kín trong cấu hình production.

Ý tưởng cốt lõi: một lớp được khai báo public vẫn có thể không truy cập được từ module khác nếu package chứa lớp đó không được export. Encapsulation của JPMS bổ sung một ranh giới ở cấp package và module bên cạnh access modifier của Java.

## 2. Tạo cấu trúc dự án mẫu

Tạo hai module:

    access-demo/
      src/
        com.example.library/
          module-info.java
          com/example/library/api/Greeter.java
          com/example/library/internal/DefaultGreeter.java
        com.example.client/
          module-info.java
          com/example/client/Main.java

Module thư viện cung cấp một API:

    package com.example.library.api;

    public interface Greeter {
        String greet(String name);
    }

Implementation nằm trong package nội bộ:

    package com.example.library.internal;

    import com.example.library.api.Greeter;

    public final class DefaultGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

Descriptor của module thư viện chỉ export API:

    module com.example.library {
        exports com.example.library.api;
    }

Package **com.example.library.internal** không xuất hiện trong exports. Vì vậy, module client không thể truy cập các kiểu trong package này theo quy tắc truy cập thông thường của JPMS.

Trong ví dụ thực tế, module library nên cung cấp một factory hoặc service API để consumer lấy implementation mà không cần biết lớp nội bộ. Bài thực hành cố ý giữ implementation class public để thấy rằng modifier public không tự vượt qua ranh giới module.

## 3. Tạo module client chỉ sử dụng API

Module client khai báo dependency tới library:

    module com.example.client {
        requires com.example.library;
    }

Lớp main sử dụng interface được export:

    package com.example.client;

    import com.example.library.api.Greeter;

    public class Main {
        public static void main(String[] args) {
            Greeter greeter = name -> "Hello, " + name;
            System.out.println(greeter.greet("Java"));
        }
    }

Ở đây client chỉ phụ thuộc vào package API. Có thể thay implementation trong library mà không cần thay đổi code consumer, miễn là contract Greeter vẫn giữ tương thích.

Nếu library có factory công khai, consumer có thể gọi factory đó:

    Greeter greeter = Greeters.defaultGreeter();

Factory có thể khởi tạo DefaultGreeter bên trong module library. Consumer không cần import lớp implementation và package internal tiếp tục được giữ kín.

## 4. Biên dịch và chạy trên module path

Từ thư mục gốc access-demo, biên dịch hai module vào thư mục mods:

    javac -d mods/com.example.library src/com.example.library/module-info.java src/com.example.library/com/example/library/api/Greeter.java src/com.example.library/com/example/library/internal/DefaultGreeter.java

    javac --module-path mods -d mods/com.example.client src/com.example.client/module-info.java src/com.example.client/com/example/client/Main.java

Chạy ứng dụng:

    java --module-path mods --module com.example.client/com.example.client.Main

Kết quả:

    Hello, Java

Client chỉ đọc API đã export. Implementation package không cần export để library tự sử dụng các lớp trong package đó.

## 5. Thử truy cập implementation package trực tiếp

Sửa client để import implementation:

    package com.example.client;

    import com.example.library.internal.DefaultGreeter;

    public class Main {
        public static void main(String[] args) {
            DefaultGreeter greeter = new DefaultGreeter();
            System.out.println(greeter.greet("Java"));
        }
    }

Biên dịch lại client:

    javac --module-path mods -d mods/com.example.client src/com.example.client/com/example/client/Main.java

Compiler sẽ báo rằng package **com.example.library.internal** không được export từ module com.example.library tới module com.example.client. Tùy phiên bản JDK và ngữ cảnh, thông báo có thể nói package không visible hoặc module không export package.

Đây là lỗi truy cập ở thời điểm biên dịch. Nguyên nhân không phải lớp DefaultGreeter thiếu modifier public; nguyên nhân là module descriptor không export package chứa lớp đó.

Để tái hiện, giữ module descriptor:

    module com.example.library {
        exports com.example.library.api;
    }

Không thêm exports cho internal trong cấu hình chuẩn. Sau khi xác nhận lỗi, khôi phục client về sử dụng Greeter API để ứng dụng chạy bình thường.

## 6. Kiểm tra lỗi access khi biên dịch và khi chạy

Cần phân biệt hai thời điểm:

| Thời điểm | Triệu chứng thường gặp | Nguyên nhân |
|---|---|---|
| Compile time | Compiler báo package không được export hoặc package không visible | Module consumer không có quyền truy cập package trong module provider |
| Link/runtime | IllegalAccessError | Bytecode hoặc cấu hình runtime yêu cầu truy cập kiểu/thành viên mà module không cho phép |
| Deep reflection | InaccessibleObjectException hoặc lỗi liên quan đến reflection | Package chưa được mở cho module thực hiện reflection |
| Readability | Module không đọc được module khác | Thiếu requires hoặc quan hệ đọc phù hợp |
| Class loading | ClassNotFoundException hoặc NoClassDefFoundError | Lớp không được tìm thấy hoặc dependency không có trong runtime configuration |

Nếu compiler chặn code, thường không thể tạo lại chính xác lỗi runtime bằng cách chạy cùng source đó. Để thử runtime access error, có thể dùng bytecode đã được biên dịch trong một cấu hình khác, reflection, hoặc một test fixture được tạo riêng. Không nên nhầm mọi lỗi access thành cùng một ngoại lệ.

Lỗi **IllegalAccessError** là lỗi liên kết xảy ra khi JVM gặp truy cập không hợp lệ tới lớp hoặc thành viên. Nó khác với **IllegalAccessException**, là checked exception thường xuất hiện từ các API reflection như Field.get hoặc Method.invoke khi quyền truy cập bị từ chối.

## 7. Dùng --add-exports trong môi trường thử nghiệm

Có thể tạm thời export package internal tới module client khi biên dịch:

    javac --module-path mods --add-exports com.example.library/com.example.library.internal=com.example.client -d mods/com.example.client src/com.example.client/module-info.java src/com.example.client/com/example/client/Main.java

Khi chạy, cần cấp quyền tương ứng cho JVM:

    java --module-path mods --add-exports com.example.library/com.example.library.internal=com.example.client --module com.example.client/com.example.client.Main

Option có dạng:

    --add-exports source-module/package=target-module

Trong ví dụ:

- Source module là com.example.library.
- Package được export thêm là com.example.library.internal.
- Target module là com.example.client.

**--add-exports** cho phép module đích truy cập các kiểu public trong package được chỉ định. Nó không tự mở package cho deep reflection và không thay đổi module-info.java của JAR.

Dùng option này để tái hiện việc truy cập package khi cần chẩn đoán hoặc kiểm thử. Không đưa nó vào lệnh production nếu package đó không phải API được hỗ trợ.

Nếu client chạy trong unnamed module, có thể dùng target **ALL-UNNAMED**. Với named module, ưu tiên chỉ định tên module cụ thể để giới hạn phạm vi truy cập.

## 8. Kiểm tra deep reflection và --add-opens

Export package cho phép truy cập các kiểu public theo quy tắc Java. Framework có thể cần thêm quyền để đọc hoặc thay đổi thành viên private qua reflection. Khi đó cần **opens**.

Thêm một test class trong module client:

    package com.example.client;

    import java.lang.reflect.Field;

    public class ReflectionProbe {
        public static void main(String[] args) throws Exception {
            Class<?> type =
                Class.forName("com.example.library.internal.DefaultGreeter");

            Field field = type.getDeclaredField("somePrivateField");
            field.setAccessible(true);
        }
    }

Ví dụ trên chỉ minh họa vị trí gọi reflection; để thử nghiệm thực tế, lớp cần có field private tên somePrivateField. Khi package chưa mở cho module client, lời gọi setAccessible(true) có thể ném **InaccessibleObjectException**.

Có thể mở package cho client trong một lần chạy:

    java --module-path mods --add-opens com.example.library/com.example.library.internal=com.example.client --module com.example.client/com.example.client.Main

Option có dạng:

    --add-opens source-module/package=target-module

**--add-opens** cho phép deep reflection từ module đích vào package được chỉ định. Nó không cấp quyền compile-time để import các kiểu trong package chưa export.

Nếu framework vừa cần import public type trong package nội bộ, vừa cần deep reflection, test configuration có thể cần cả --add-exports khi biên dịch và --add-opens khi chạy. Chỉ cấp những quyền thực sự cần thiết.

## 9. So sánh exports, opens và các runtime options

| Cơ chế | Mục đích | Ví dụ sử dụng |
|---|---|---|
| exports | Công khai package cho truy cập thông thường | API public của thư viện |
| qualified exports | Công khai package cho module đích cụ thể | SPI dành cho một adapter module |
| opens | Cho phép deep reflection | ORM đọc field private |
| --add-exports | Bổ sung export trong cấu hình compile/runtime | Test truy cập public implementation type |
| --add-opens | Bổ sung open trong runtime | Test framework cần reflection sâu |
| --add-reads | Bổ sung readability | Module cần đọc một module khác trong cấu hình đặc biệt |

Không dùng --add-exports để giải quyết lỗi deep reflection nếu package cần được mở. Không dùng --add-opens để sửa lỗi compiler không thể import package. Hãy xác định đúng loại access đang bị chặn.

## 10. Kiểm tra module descriptor và module resolution

Có thể xem module descriptor của artifact:

    jar --describe-module --file mods/com.example.library

Kết quả cần cho thấy package API được export và package internal không được export. Nếu module descriptor được đóng gói trong JAR, chạy lệnh trên file JAR tương ứng.

Để quan sát module resolution:

    java --show-module-resolution --module-path mods --module com.example.client/com.example.client.Main

Option này hiển thị module nào được resolve và quan hệ dependency. Nó giúp chẩn đoán readability và module path, nhưng không tự giải quyết package access.

Nếu module không được tìm thấy, kiểm tra module path. Nếu module được tìm thấy nhưng package không được truy cập, kiểm tra exports. Nếu lỗi chỉ xảy ra với reflection, kiểm tra opens. Không thêm mọi option cùng lúc vì như vậy khó xác định nguyên nhân gốc.

## 11. Thiết kế production và test configuration

Trong production, module descriptor nên giữ ranh giới dự kiến:

    module com.example.library {
        exports com.example.library.api;
    }

Test có thể dùng một cấu hình riêng:

- Test black-box chỉ cần requires library và gọi public API.
- Test cần import một public implementation type có thể dùng --add-exports trong test compile/runtime.
- Framework cần deep reflection có thể dùng --add-opens trong test JVM.
- Test cần package-private access có thể dùng --patch-module để đưa test classes vào module đích trong test runtime.

Không sửa module-info.java production chỉ để test biên dịch được. Không lưu các option test-only vào script deploy hoặc launcher production.

Nếu dùng Maven hoặc Gradle, đặt option trong cấu hình test task tương ứng. Tên property và cách truyền JVM argument tùy plugin/build tool; hãy bảo đảm option được truyền cho cả compiler nếu cần compile-time access và test JVM nếu cần runtime reflection.

## 12. Ghi nhớ

- Public class trong package không export vẫn không thể được module khác truy cập thông thường.
- **exports** công khai package; **opens** cho phép deep reflection.
- Compile error về package không visible khác với IllegalAccessError ở runtime.
- IllegalAccessException và InaccessibleObjectException là những lỗi reflection khác nhau, cần xem đúng API gây lỗi.
- --add-exports có thể cấp quyền truy cập kiểu public trong package cho module đích.
- --add-opens cấp quyền deep reflection trong runtime, không thay thế compile-time export.
- Chỉ dùng runtime options để chẩn đoán hoặc cho test khi cần; giữ module descriptor production nhỏ và rõ.
- Kiểm tra module path, requires, exports và opens theo đúng loại lỗi.
- Dùng jar --describe-module và --show-module-resolution để quan sát cấu hình thực tế.

**Ẩn implementation package giúp module giữ quyền kiểm soát API và giới hạn điểm truy cập từ bên ngoài.** Khi kiểm tra lỗi access, hãy xác định lỗi xảy ra lúc biên dịch, liên kết hay reflection rồi chọn đúng cơ chế JPMS thay vì export hoặc open toàn bộ module.

## Tài liệu tham khảo

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html