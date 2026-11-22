# Unnamed module đọc mọi named module được export

## 1. Unnamed module trong JPMS

Khi Java chạy ứng dụng theo classpath, các class của ứng dụng không thuộc một named module có module descriptor. Chúng thuộc **unnamed module** gắn với class loader đã định nghĩa chúng.

Mỗi class loader có unnamed module riêng. Trong ứng dụng thông thường, class loader hệ thống (application class loader) định nghĩa các class trên classpath và có unnamed module tương ứng.

Unnamed module có một số đặc điểm quan trọng:

- Không có tên module và không có module descriptor riêng.
- Không khai báo requires, exports hoặc opens trong module-info.java.
- Đọc các named module trong cấu hình module tương ứng.
- Các package của unnamed module được export và open để những module khác có thể truy cập theo các quy tắc tương ứng.
- Không thể được một named module tham chiếu bằng chỉ thị requires thông thường vì unnamed module không có tên.

Đặc điểm “đọc mọi named module” giúp ứng dụng cũ trên classpath có thể sử dụng API được công khai bởi các module đã được phân giải. Nhờ đó, ứng dụng có thể tiếp tục chạy theo cách truyền thống trong khi dùng một số thư viện đã chuyển sang JPMS.

## 2. Đọc module và truy cập package là hai điều kiện riêng

Trong JPMS, một module đọc được module khác chưa có nghĩa là mọi package của module đó đều có thể truy cập.

Để class trong unnamed module sử dụng một type public của named module, cần có các điều kiện chính:

1. **Named module phải được phân giải** trong cấu hình module đang chạy.
2. **Unnamed module phải đọc named module đó** theo quan hệ đọc của cấu hình.
3. **Package chứa type phải được export tới unnamed module**.
4. **Type và thành viên cần dùng phải có mức truy cập phù hợp** theo quy tắc Java, thường là public.

Có thể hình dung:

~~~text
Ứng dụng trên classpath
        |
        v
Unnamed module
        |
        | reads
        v
Named module đã được phân giải
        |
        | exports package.api
        v
Type public trong package.api
        |
        v
Ứng dụng có thể import và sử dụng
~~~

Với một dòng exports không giới hạn, package được công khai cho tất cả module đọc module cung cấp, bao gồm unnamed module. Nếu package không được export, việc unnamed module có khả năng đọc named module vẫn không đủ để truy cập type trong package đó.

## 3. Named module export package cho unnamed module

Giả sử thư viện đã được modular hóa:

~~~text
com.acme.library/
├── module-info.java
└── com/acme/library/api/
    └── Greeting.java
~~~

Module descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Type public:

~~~java
package com.acme.library.api;

public class Greeting {
    public static String message() {
        return "Hello from a named module";
    }
}
~~~

Dòng exports com.acme.library.api công khai package API. Một ứng dụng nằm trên classpath có thể import Greeting nếu module com.acme.library đã được phân giải trong lần chạy đó.

Ứng dụng classpath:

~~~text
app/
└── com/acme/app/Main.java
~~~

Mã ứng dụng:

~~~java
package com.acme.app;

import com.acme.library.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Ứng dụng không cần module-info.java. Khi được chạy từ classpath, Main thuộc unnamed module của application class loader.

## 4. Kết hợp classpath và module path khi chạy

Classpath và module path có thể cùng xuất hiện trong một lệnh Java. Classpath chứa ứng dụng truyền thống; module path chứa thư viện modular.

Ví dụ, sau khi biên dịch thư viện thành modular JAR:

~~~text
project/
├── app/
│   └── com/acme/app/Main.class
└── mods/
    └── com.acme.library.jar
~~~

Chạy ứng dụng trên classpath và đưa module thư viện vào cấu hình bằng --add-modules:

~~~bash
java --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Ở đây:

- --module-path mods cho Java biết vị trí tìm named module.
- --add-modules com.acme.library yêu cầu đưa module thư viện vào tập module gốc để được phân giải.
- -cp app đặt class ứng dụng trên classpath.
- com.acme.app.Main là lớp main được chạy từ unnamed module.

Nếu module thư viện đã được phân giải và export package API không giới hạn, ứng dụng classpath có thể sử dụng type public trong package đó.

Không nên giả định mọi JAR nằm trên module path đều tự động được phân giải. Một module chỉ có thể được sử dụng nếu nó tham gia cấu hình module của tiến trình. Khi cần xác định rõ một module thư viện, --add-modules là cách tường minh.

Có thể dùng ALL-MODULE-PATH với --add-modules để đưa tất cả module quan sát được trên module path vào tập gốc:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     -cp app \
     com.acme.app.Main
~~~

Đây là lựa chọn rộng. Với ứng dụng có dependency đã biết, nên chỉ định module cần thiết để cấu hình chạy dễ hiểu và dễ kiểm soát.

## 5. Vì sao unnamed module có thể đọc named module?

Named module mô tả phụ thuộc bằng requires. Unnamed module không có module descriptor để khai báo từng dependency, nên JPMS áp dụng quy tắc đọc đặc biệt cho nó.

Nhờ khả năng đọc các named module trong cấu hình tương ứng, ứng dụng classpath có thể tiếp tục sử dụng API modular mà không phải chuyển ngay toàn bộ ứng dụng thành named module.

Ví dụ, nếu module thư viện khai báo:

~~~java
module com.acme.format {
    exports com.acme.format.api;
}
~~~

thì class trên classpath có thể import type public thuộc com.acme.format.api khi com.acme.format đã được phân giải và package được export không giới hạn.

Cơ chế này hỗ trợ chuyển đổi từng phần:

~~~text
Ứng dụng cũ trên classpath
          |
          | unnamed module
          |
          +------> Named module A (export API)
          |
          +------> Named module B (export API)
          |
          +------> Named module C (export API)
~~~

Ứng dụng không cần chuyển thành named module chỉ để dùng các thư viện modular. Tuy nhiên, việc giữ ứng dụng trên classpath cũng đồng nghĩa ứng dụng chưa có module descriptor để khai báo phụ thuộc, export API riêng hoặc thiết lập ranh giới package của chính nó.

## 6. Phạm vi của unnamed module gắn với class loader

Unnamed module không phải một module toàn cục duy nhất cho mọi class trong JVM. Mỗi class loader có unnamed module riêng.

Điều này quan trọng trong ứng dụng có plugin hoặc custom class loader:

- Class do application class loader định nghĩa thuộc unnamed module của application class loader.
- Class do một custom class loader định nghĩa thuộc unnamed module gắn với loader đó.
- Hai class có cùng tên đầy đủ nhưng do hai class loader khác nhau định nghĩa vẫn có thể là hai kiểu khác nhau trong JVM.
- Khả năng đọc và khả năng tìm class phụ thuộc vào module, layer và class loader liên quan.

Vì vậy, khi một ứng dụng dùng nhiều class loader, không nên chỉ nhìn vào một classpath chung rồi kết luận mọi class đều có cùng quyền đọc module. Hãy xác định loader nào định nghĩa class consumer và loader/layer nào cung cấp named module.

## 7. Unnamed module không thể được named module requires trực tiếp

Chiều đọc giữa unnamed module và named module không đối xứng.

Unnamed module có thể đọc named module, nhưng named module không tự động đọc unnamed module. Vì unnamed module không có tên, không thể viết:

~~~java
module com.acme.plugin {
    requires unnamed;
}
~~~

Cú pháp trên không hợp lệ vì không có module tên unnamed để requires.

Nếu named module cần đọc class nằm trên classpath trong một tình huống tương thích, có thể bổ sung quan hệ đọc bằng tùy chọn chạy:

~~~bash
java --add-reads com.acme.plugin=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.plugin \
     -cp app \
     --module com.acme.plugin/com.acme.plugin.Main
~~~

Tùy chọn --add-reads source=target bổ sung quan hệ đọc ở runtime. ALL-UNNAMED đại diện cho các unnamed module liên quan trong ngữ cảnh launcher.

Đây là biện pháp tương thích có chủ đích. Thiết kế modular ổn định nên đặt hợp đồng dùng chung trong một named API module để các named module có thể khai báo requires rõ ràng.

## 8. Unnamed module chỉ truy cập package được export phù hợp

Một named module có thể export package không giới hạn:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Khi đó, unnamed module có thể truy cập type public trong package com.acme.library.api nếu module đã được phân giải.

Nhưng nếu module chỉ qualified export cho một named module:

~~~java
module com.acme.library {
    exports com.acme.library.api to com.acme.application;
}
~~~

thì package chỉ được export cho module có tên com.acme.application. Unnamed module không phải module đích có tên com.acme.application, vì vậy không nhận được quyền truy cập từ qualified export này.

Nếu ứng dụng classpath cần quyền truy cập package đó trong một tình huống tương thích, launcher có thể bổ sung export tới ALL-UNNAMED:

~~~bash
java --add-exports com.acme.library/com.acme.library.api=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Cú pháp tổng quát:

~~~text
--add-exports source.module/package=target.module
~~~

ALL-UNNAMED là tên đích đặc biệt dành cho các tùy chọn launcher như --add-exports. Nó không phải tên module hợp lệ để ghi vào requires hoặc qualified exports trong module-info.java.

Không nên dùng --add-exports=...=ALL-UNNAMED để mở mọi package nội bộ. Chỉ bổ sung package thực sự cần thiết và cân nhắc chuyển API cần dùng sang package được export công khai.

## 9. Public vẫn phải tuân theo quy tắc truy cập Java

Ngay cả khi unnamed module đọc named module và package đã được export, các access modifier của Java vẫn có hiệu lực.

Ví dụ:

~~~java
package com.acme.library.api;

public class Greeting {
    public String hello() {
        return "Hello";
    }

    protected void extensionHook() {
    }

    void reset() {
    }

    private void internalOperation() {
    }
}
~~~

Từ mã thuộc package khác trên classpath:

- Có thể gọi hello trên một instance hợp lệ.
- extensionHook vẫn bị giới hạn bởi quy tắc protected, chẳng hạn phải nằm trong ngữ cảnh subclass phù hợp.
- reset là package-private nên không thể gọi từ package khác.
- internalOperation là private nên chỉ có thể truy cập theo quy tắc private của Java.

Tương tự, type không public không trở thành public chỉ vì package của nó được export:

~~~java
package com.acme.library.api;

class InternalMapper {
}
~~~

Ứng dụng bên ngoài package không thể import InternalMapper. exports mở package ở cấp module; nó không bỏ qua quy tắc truy cập của ngôn ngữ.

## 10. Phân biệt exports với opens

Một unnamed module có thể truy cập API public trong package được export. Điều đó không có nghĩa nó được deep reflection vào private member của module nguồn.

- **exports** cho phép truy cập Java thông thường vào các type public và thành viên được phép.
- **opens** cho phép deep reflection vào các thành viên không public của package.
- **open module** mở tất cả package của module cho deep reflection.

Ví dụ module thư viện:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.model;
}
~~~

Ứng dụng classpath có thể sử dụng API public trong com.acme.library.api. Nhưng nếu framework cần truy cập field private trong com.acme.library.model, package đó cần được mở phù hợp.

Có thể dùng --add-opens để mở package cho unnamed modules trong runtime:

~~~bash
java --add-opens com.acme.library/com.acme.library.model=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Không dùng exports để thay thế opens khi lỗi thực sự là InaccessibleObjectException do deep reflection.

## 11. Quan sát module và kiểm tra quyền đọc

Có thể dùng API Module để quan sát module của một class:

~~~java
Class<?> type = com.acme.app.Main.class;
Module module = type.getModule();

System.out.println("Module name: " + module.getName());
System.out.println("Is named: " + module.isNamed());
System.out.println("Class loader: " + type.getClassLoader());
~~~

Với class thuộc unnamed module, getName() trả về null và isNamed() trả về false. Module descriptor của unnamed module cũng không có giá trị như một named module.

Có thể kiểm tra quan hệ đọc tới module khác:

~~~java
Module consumer = Main.class.getModule();
Module library = com.acme.library.api.Greeting.class.getModule();

System.out.println(consumer.canRead(library));
~~~

Nếu kết quả là true, consumer đọc được module library. Điều đó chưa xác nhận package cụ thể đã được export; cần kiểm tra descriptor của module nguồn hoặc API tương ứng.

Để xem module descriptor của JAR:

~~~bash
jar --describe-module --file mods/com.acme.library.jar
~~~

Để xem module nào được phân giải khi khởi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Hai lệnh hỗ trợ xác định riêng hai vấn đề: module đã được phân giải hay chưa, và package API có được export hay không.

## 12. Lỗi thường gặp khi ứng dụng classpath dùng named module

**Module không được phân giải**

JAR có trên module path nhưng module không nằm trong cấu hình chạy. Bổ sung module làm root bằng --add-modules hoặc điều chỉnh cấu hình module phù hợp.

**Package không được export**

Unnamed module đọc module nguồn nhưng package chứa type không được export. Cập nhật module descriptor của thư viện nếu package thuộc API công khai; trong trường hợp tương thích tạm thời, cân nhắc --add-exports với phạm vi hẹp.

**Qualified export chỉ dành cho named module khác**

Package được export tới một module có tên cụ thể, nên unnamed module không nhận quyền. Nếu ứng dụng classpath thật sự cần truy cập, dùng API công khai không giới hạn hoặc cấu hình --add-exports ...=ALL-UNNAMED có chủ đích.

**Type hoặc member không public**

Package đã export nhưng class hoặc member cần dùng không có mức truy cập phù hợp. Sửa thiết kế API nếu type đó thực sự cần công khai; không tăng mức truy cập tùy tiện cho chi tiết triển khai.

**Named module cần đọc classpath**

Chiều ngược lại không tự có. Named module không thể requires unnamed module. Nếu cần tương thích, dùng --add-reads module=ALL-UNNAMED hoặc chuyển hợp đồng chung vào một named module.

**Framework cần deep reflection**

Package được export nhưng không được mở. Bổ sung opens hoặc --add-opens đúng package cho module framework; không mở rộng toàn bộ module nếu không cần.

## 13. Ghi nhớ

- Classpath application được đặt trong unnamed module gắn với class loader đã định nghĩa class.
- Unnamed module có quan hệ đọc tới các named module trong cấu hình tương ứng, nhưng module phải được phân giải trước.
- Đọc module và truy cập package là hai điều kiện riêng: package vẫn phải được export phù hợp.
- Unqualified exports cho phép mọi module đọc nguồn truy cập package; qualified exports chỉ cho các named module đích đã nêu.
- Named module không tự động đọc unnamed module và không thể requires một unnamed module.
- --add-modules có thể đưa named module vào tập root; --add-exports và --add-reads bổ sung quyền truy cập có giới hạn khi cần tương thích.
- public, protected, package-private và private vẫn tuân theo quy tắc Java.
- exports dành cho API thông thường; opens dành cho deep reflection.

Khi kết hợp ứng dụng classpath với thư viện modular, hãy xác định class consumer thuộc unnamed module nào, module thư viện đã được phân giải chưa, và package API có export tới consumer hay không. Ba thông tin này giúp phân biệt lỗi module resolution với lỗi truy cập package hoặc member.
