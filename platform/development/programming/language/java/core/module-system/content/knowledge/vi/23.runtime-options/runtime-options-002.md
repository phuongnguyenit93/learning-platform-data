# --add-exports mở export tạm thời

## 1. Mục tiêu

Java Platform Module System (JPMS) kiểm soát package nào của một module được module khác truy cập. Một module có thể khai báo package được export công khai bằng directive **exports**, hoặc chỉ export cho một số module cụ thể bằng qualified export. Các package không được export sẽ được đóng đối với truy cập thông thường từ module khác.

Tùy chọn **--add-exports** của JDK cho phép bổ sung một export trong lúc biên dịch hoặc khởi chạy ứng dụng. Đây là cách cấp quyền truy cập có phạm vi hẹp để tương thích với thư viện cũ, kiểm tra một module hoặc xử lý tình huống triển khai cần thiết mà không sửa module descriptor của module nguồn.

Sau bài học, bạn có thể:
- Đọc và viết đúng cú pháp **--add-exports**.
- Chọn đúng module nguồn, package và module đích.
- Phân biệt quyền export với quyền đọc module và quyền truy cập reflection sâu.
- Cấp quyền ở compile time và runtime khi cần.
- Dùng **ALL-UNNAMED** cho mã chạy trong unnamed module.
- Nhận biết giới hạn và rủi ro khi phụ thuộc vào API nội bộ của JDK.

## 2. Vì sao cần --add-exports?

Trong JPMS, mỗi package thuộc về một module. Module nguồn có thể công khai package của nó cho module khác bằng directive trong **module-info.java**:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Ở ví dụ này, module khác đọc được module **com.example.library** và có thể truy cập các kiểu public trong package **com.example.api**.

Nếu package không được export, một module khác không thể truy cập các public type của package đó theo quy tắc truy cập module thông thường. Việc class hoặc method được khai báo public trong mã nguồn không đủ để vượt qua ranh giới module: module system còn kiểm tra package có được export cho module đang truy cập hay không.

Có trường hợp ứng dụng cần truy cập một package chưa được export:

- Thư viện cũ phụ thuộc vào một API nội bộ của JDK.
- Một ứng dụng cần dùng package chỉ được export có điều kiện cho module khác.
- Nhóm phát triển cần chạy một kiểm thử tương thích trong môi trường có cấu hình module chặt chẽ.
- Ứng dụng đang chuyển đổi dần sang API công khai và cần một giải pháp tạm thời trong thời gian migration.

**--add-exports** bổ sung một quan hệ export khi chạy hoặc biên dịch. Tùy chọn này không sửa file **module-info.class**, không thay đổi JAR trên đĩa và không tạo ra một export vĩnh viễn trong module nguồn. Quyền bổ sung chỉ áp dụng cho tiến trình hoặc môi trường biên dịch được cấu hình bằng tùy chọn đó.

## 3. Cú pháp và cách đọc

Cú pháp tổng quát:

~~~text
--add-exports source-module/package=target-module(,target-module)*
~~~

Có thể đọc thành:

> Export package **package** của module **source-module** cho module đích **target-module**.

Ví dụ:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Trong lệnh trên:

- **java.base** là module nguồn chứa package cần truy cập.
- **sun.nio.ch** là package được export bổ sung.
- **ALL-UNNAMED** là module đích, nghĩa là tất cả unnamed module.
- Phần còn lại là classpath và lớp main được khởi chạy.

Tên module và tên package phân biệt chữ hoa/chữ thường. Dấu gạch chéo phân tách module nguồn với package; dấu bằng phân tách package với module đích. Không thêm dấu gạch chéo ở cuối package, không ghi tên class thay cho package, và không bỏ tên module nguồn.

Có thể cấp quyền cho nhiều module đích bằng danh sách phân tách bởi dấu phẩy:

~~~text
--add-exports java.base/sun.nio.ch=com.example.app,com.example.test
~~~

Hoặc lặp lại tùy chọn để export nhiều package:

~~~text
--add-exports java.base/sun.nio.ch=ALL-UNNAMED
--add-exports java.base/jdk.internal.misc=com.example.app
~~~

Mỗi tùy chọn chỉ chỉ định một cặp module nguồn/package. Nếu có nhiều package cần truy cập, khai báo từng package riêng để phạm vi quyền được thể hiện rõ ràng.

## 4. Module nguồn và module đích

### Module nguồn

Module nguồn là module **sở hữu package**. Trong ví dụ **java.base/sun.nio.ch**, module **java.base** sở hữu package **sun.nio.ch**.

Có thể xem module và package thuộc về JDK bằng công cụ:

~~~bash
java --describe-module java.base
~~~

Để xem descriptor của một modular JAR:

~~~bash
jar --describe-module --file library.jar
~~~

Không suy đoán module nguồn chỉ từ tên package. Hãy xác định package thực sự thuộc module nào trong JDK hoặc trong module ứng dụng.

### Module đích

Module đích là module được cấp quyền truy cập package. Nếu ứng dụng là named module, hãy dùng đúng tên module trong module descriptor.

Ví dụ:

~~~bash
java --add-exports java.base/sun.nio.ch=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

Ở đây chỉ module **com.example.app** nhận export bổ sung. Các module khác không tự động nhận quyền truy cập package đó.

Nếu ứng dụng chạy trên classpath, các lớp ứng dụng thuộc unnamed module. Khi đó dùng **ALL-UNNAMED**:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

**ALL-UNNAMED** bao gồm các unnamed module, thường gặp khi chạy ứng dụng hoặc thư viện trên classpath. Nó không có nghĩa là export cho tất cả named module. Dùng giá trị này sẽ cấp quyền rộng hơn so với việc chỉ định một named module cụ thể.

## 5. Export và readability là hai điều kiện khác nhau

Để module đích truy cập một public type trong module nguồn, hai điều kiện quan trọng là:

1. Module đích phải **đọc được (read)** module nguồn.
2. Package chứa type phải được **export** cho module đích.

**--add-exports** chỉ bổ sung điều kiện thứ hai. Nó không tự động tạo quan hệ readability.

Trong nhiều ví dụ với **java.base**, module ứng dụng đã đọc được module này vì mọi module đều có readability tới java.base. Nhưng với một module thư viện khác, ứng dụng có thể cần thêm directive **requires** trong module-info.java.

Nếu không thể sửa module descriptor của module đích, tùy chọn **--add-reads** có thể bổ sung quan hệ đọc trong thời gian chạy:

~~~text
--add-reads target-module=source-module
~~~

Ví dụ:

~~~bash
java --add-reads com.example.app=com.example.library --add-exports com.example.library/com.example.internal=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

Lệnh minh họa bổ sung hai quyền riêng biệt: module **com.example.app** đọc được **com.example.library**, và package **com.example.internal** được export cho ứng dụng. Nếu module descriptor đã có **requires com.example.library**, phần **--add-reads** thường không cần thiết.

Đừng dùng **--add-exports** để sửa lỗi module không đọc được dependency. Hãy xác định điều kiện nào đang thiếu và chỉ bổ sung đúng quyền cần thiết.

## 6. --add-exports ở compile time

Nếu mã nguồn tham chiếu một public type thuộc package chưa được export, trình biên dịch có thể từ chối mã dù type đó là public.

Có thể truyền **--add-exports** cho **javac**:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out src/com/example/Main.java
~~~

Tùy chọn này cho phép trình biên dịch xem package **sun.nio.ch** của module **java.base** là được export cho unnamed module trong lần biên dịch đó.

Ví dụ minh họa mã nguồn tham chiếu một type nội bộ:

~~~java
package com.example;

import sun.nio.ch.DirectBuffer;

import java.nio.ByteBuffer;

public class Main {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(16);
        DirectBuffer internalBuffer = (DirectBuffer) buffer;
        System.out.println(internalBuffer.address());
    }
}
~~~

Khi biên dịch, JDK có thể phát cảnh báo rằng **DirectBuffer** là API nội bộ và có thể bị loại bỏ hoặc thay đổi trong bản phát hành tương lai. **--add-exports** xử lý ranh giới export của module; nó không biến API nội bộ thành API công khai, ổn định hoặc được hỗ trợ.

Với named module, dùng tên module đích:

~~~bash
javac --add-exports java.base/sun.nio.ch=com.example.app --module-path mods -d out --module-source-path src -m com.example.app
~~~

Ví dụ này minh họa vị trí của tùy chọn khi biên dịch module; cấu trúc source tree và danh sách module phải phù hợp với dự án thực tế.

## 7. --add-exports ở runtime

Việc biên dịch thành công không có nghĩa là chương trình sẽ chạy được. Tùy chọn cấp export cho **javac** chỉ áp dụng trong môi trường biên dịch. Khi chạy, JVM tạo module graph riêng và cần được cấp export tương ứng.

Với ứng dụng trên classpath:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.example.Main
~~~

Với ứng dụng là named module:

~~~bash
java --module-path mods --add-exports java.base/sun.nio.ch=com.example.app --module com.example.app/com.example.Main
~~~

Các tùy chọn JVM phải được đặt trước phần chỉ định ứng dụng hoặc module cần chạy. Ví dụ, đặt **--add-exports** trước **--module** trong lệnh chạy modular application.

Nếu ứng dụng được khởi chạy bởi script, service manager, IDE, application server, test runner hoặc container, phải cấu hình tùy chọn ở đúng nơi tạo tiến trình JVM. Thêm tùy chọn vào một lệnh build không đảm bảo nó xuất hiện trong tiến trình runtime.

Khi chạy ứng dụng bằng **java -jar**, ứng dụng JAR được chạy theo cơ chế classpath/unnamed module. Nếu muốn chạy một modular JAR như named module, hãy dùng **--module-path** và **--module** thay vì dựa vào **-jar**.

## 8. Phân biệt --add-exports và --add-opens

Hai tùy chọn có tên gần giống nhau nhưng mục đích khác nhau.

| Tùy chọn | Mục đích | Thời điểm |
|---|---|---|
| **--add-exports** | Cho module đích truy cập các public type và public/protected member của package được export | Có thể dùng khi biên dịch và khi chạy |
| **--add-opens** | Cho phép deep reflection vào package, kể cả truy cập reflective tới thành viên không public theo các điều kiện reflection | Runtime |
| **--add-reads** | Bổ sung quan hệ readability để module đích đọc module nguồn | Runtime |

Nếu mã nguồn có câu lệnh import và gọi một public class nằm trong package chưa export, hãy xem xét **--add-exports**.

Nếu framework dùng reflection để truy cập private field, private constructor hoặc thành viên không public của một package thuộc named module, vấn đề thường liên quan đến **--add-opens**. Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Tùy chọn trên mở package **java.lang** cho deep reflection từ unnamed module. Nó không làm cho mã nguồn có thể import một class nội bộ của package đó khi biên dịch.

**--add-opens** không phải cách thay thế tổng quát cho **--add-exports**. Ngược lại, **--add-exports** cũng không cho phép framework bỏ qua mọi ranh giới reflection để đọc/ghi thành viên private.

## 9. Quan hệ với exports trong module-info.java

Có hai cách tạo quan hệ export:

**Export lâu dài do module nguồn khai báo:**

~~~java
module com.example.library {
    exports com.example.api;
    exports com.example.legacy to com.example.app;
}
~~~

Directive thứ nhất export **com.example.api** cho mọi module đọc module nguồn. Directive thứ hai chỉ export **com.example.legacy** cho **com.example.app**.

**Export bổ sung từ dòng lệnh:**

~~~bash
java --add-exports com.example.library/com.example.internal=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

Cách thứ hai không sửa module descriptor. Nó thêm một export trong module configuration của tiến trình. Vì vậy:

- Nếu bạn sở hữu module nguồn và package là API mà các module khác cần dùng lâu dài, hãy cân nhắc khai báo **exports** trong module-info.java.
- Nếu chỉ cần cấp quyền tương thích cho một ứng dụng cụ thể, tùy chọn dòng lệnh có thể phù hợp hơn.
- Nếu package là API nội bộ của JDK, hãy ưu tiên API công khai được hỗ trợ thay vì biến tùy chọn này thành phụ thuộc lâu dài.
- Nếu module nguồn thay đổi tên hoặc package, dòng lệnh cũ có thể không còn đúng.

Qualified export trong module descriptor có thể chỉ cho một số module truy cập. **--add-exports** bổ sung target module khác vào phạm vi export ở runtime/compile-time tương ứng; nó không viết lại directive gốc.

## 10. Ví dụ đầy đủ: ứng dụng trên classpath

Giả sử ứng dụng có một class dùng type **sun.nio.ch.DirectBuffer**:

~~~java
package com.example;

import java.nio.ByteBuffer;
import sun.nio.ch.DirectBuffer;

public class Main {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(32);
        DirectBuffer direct = (DirectBuffer) buffer;
        System.out.println(direct.address());
    }
}
~~~

Biên dịch:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out src/com/example/Main.java
~~~

Chạy:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.example.Main
~~~

Cả hai giai đoạn đều cần tùy chọn. Nếu bỏ tùy chọn ở compile time, javac có thể báo package không được export. Nếu biên dịch đã thành công nhưng bỏ tùy chọn ở runtime, JVM có thể ném **IllegalAccessError** khi mã cố truy cập type đó.

Ví dụ dùng API nội bộ chỉ nhằm minh họa cơ chế. Trong ứng dụng thực tế, hãy tìm API được hỗ trợ thay thế trước khi áp dụng cách này.

## 11. Ví dụ đầy đủ: ứng dụng trên module path

Giả sử module ứng dụng có descriptor:

~~~java
module com.example.app {
    requires java.base;
}
~~~

Mã nguồn trong module sử dụng một public type thuộc package **sun.nio.ch**. Có thể biên dịch với export bổ sung:

~~~bash
javac --add-exports java.base/sun.nio.ch=com.example.app --module-source-path src -d mods -m com.example.app
~~~

Sau khi biên dịch, chạy module với cùng export:

~~~bash
java --module-path mods --add-exports java.base/sun.nio.ch=com.example.app --module com.example.app/com.example.Main
~~~

Ở đây module đích là **com.example.app**, vì mã đang chạy trong named module. Không dùng **ALL-UNNAMED** cho ví dụ này vì ứng dụng không thuộc unnamed module.

Nếu ứng dụng phụ thuộc vào module khác ngoài java.base, hãy bảo đảm descriptor có **requires** tương ứng hoặc cấu hình readability thích hợp. Export bổ sung không thay thế dependency của ứng dụng.

## 12. Cấu hình trong build và môi trường chạy

Trong dự án dùng Maven hoặc Gradle, cần phân biệt compiler arguments và runtime JVM arguments.

- **Compile:** truyền tùy chọn cho compiler plugin hoặc task biên dịch để mã nguồn nhìn thấy package cần dùng.
- **Test:** truyền tùy chọn cho JVM chạy test. Một số test runner fork tiến trình riêng nên cấu hình ở JVM của Maven/Gradle không nhất thiết tự động áp dụng cho tiến trình fork.
- **Run:** truyền tùy chọn cho application run task, script khởi chạy hoặc cấu hình JVM của IDE.
- **Deploy:** cập nhật cấu hình của service/container thực sự khởi chạy ứng dụng; sau đó kiểm tra command line hoặc log khởi động để xác nhận tùy chọn đã được áp dụng.

Đừng chỉ thêm **--add-exports** vào cấu hình compile rồi cho rằng vấn đề đã được giải quyết. Hãy xác định tiến trình nào thực sự cần truy cập package và cấu hình ở đúng giai đoạn.

Trong môi trường CI, có thể đưa tùy chọn vào cấu hình tập trung để các lệnh compile, test và run sử dụng nhất quán. Ghi chú rõ module/package/target và lý do cần quyền truy cập để nhóm vận hành biết khi nào có thể gỡ bỏ.

## 13. Giới hạn và rủi ro

**--add-exports** là một cơ chế tương thích, không phải lời hứa về ổn định API.

Các package như **sun.nio.ch**, **jdk.internal.misc** hoặc những package nội bộ khác không thuộc API công khai được hỗ trợ. Cấu trúc, tên lớp, method và hành vi có thể thay đổi giữa các phiên bản JDK. Một lệnh chạy được trên JDK hiện tại có thể thất bại sau khi nâng cấp JDK.

Tùy chọn này cũng làm yếu ranh giới đóng gói module cho module đích. Nếu cấp export cho **ALL-UNNAMED**, mọi unnamed module trong tiến trình có thể truy cập package được export. Điều đó rộng hơn việc cấp cho một named module cụ thể.

Một số nguyên tắc vận hành:

1. Cấp quyền cho đúng package và đúng target module.
2. Tránh export cho **ALL-UNNAMED** nếu có thể chỉ định một named module.
3. Không cấp quyền rộng chỉ để làm một lỗi khác biến mất.
4. Ghi rõ lý do, người sở hữu và điều kiện gỡ bỏ tùy chọn.
5. Kiểm tra lại khi nâng cấp JDK hoặc thư viện.
6. Theo dõi cảnh báo compiler về API nội bộ và lập kế hoạch thay thế.
7. Không nhầm việc truy cập thành công với việc API đó được hỗ trợ hoặc bảo đảm tương thích.

Từ JDK 17, strong encapsulation của các package nội bộ trong JDK được áp dụng chặt chẽ hơn. Tùy chọn **--illegal-access** cũ không còn là cách chung để mở các package này. Nếu cần truy cập một package cụ thể, hãy hiểu rõ và dùng đúng tùy chọn **--add-exports** hoặc **--add-opens** theo loại truy cập.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| javac báo package không được export | Thiếu export ở compile time hoặc sai module/package | Thêm --add-exports vào javac với đúng source module và target |
| Chạy gặp IllegalAccessError | Compile có quyền nhưng JVM runtime không có export | Thêm cùng tùy chọn vào lệnh java |
| Module không đọc được type của module khác | Thiếu readability, không phải export | Kiểm tra requires hoặc --add-reads |
| Reflection báo InaccessibleObjectException | Cần deep reflection vào package chưa mở | Xem xét --add-opens cho target module |
| Vẫn lỗi dù đã thêm tùy chọn | Sai module nguồn, package, target module hoặc tùy chọn đặt sai tiến trình | Xác định module chứa class, module gọi và JVM thực sự khởi chạy |
| Classpath chạy được nhưng named module lỗi | Target module khác nhau hoặc descriptor thiếu requires | Dùng đúng tên named module và kiểm tra module graph |
| Nâng cấp JDK thì lỗi | API nội bộ đã thay đổi hoặc bị loại bỏ | Chuyển sang API công khai và kiểm tra release notes |

Khi chẩn đoán, hãy lấy thông báo lỗi đầy đủ, xác định class đang truy cập, package chứa class, module sở hữu package và module đích. Sau đó kiểm tra cả command line của compiler lẫn command line runtime. Không suy luận rằng tùy chọn đã có trong một file cấu hình nghĩa là tiến trình JVM chắc chắn đã nhận được nó.

## 15. Tự kiểm tra

**1. --add-exports java.base/sun.nio.ch=ALL-UNNAMED có nghĩa gì?**

Nó bổ sung export package **sun.nio.ch** của module **java.base** cho tất cả unnamed module trong phạm vi cấu hình. Đây thường là cách cấp quyền cho mã ứng dụng chạy trên classpath.

**2. --add-exports có sửa module-info.class không?**

Không. Tùy chọn chỉ bổ sung export trong môi trường compile hoặc runtime tương ứng; file module descriptor trên đĩa không bị thay đổi.

**3. Vì sao cần thêm tùy chọn cả khi biên dịch và khi chạy?**

Vì javac và JVM có module configuration riêng. Tùy chọn lúc biên dịch cho phép mã nguồn tham chiếu package; tùy chọn runtime cho phép bytecode thực sự truy cập package khi ứng dụng chạy.

**4. --add-exports có cho phép truy cập private field bằng reflection không?**

Không. Nó export package cho truy cập thông thường tới public type/member. Deep reflection vào thành viên không public thường cần **--add-opens** ở runtime.

**5. --add-exports có tự động làm module đích đọc được module nguồn không?**

Không. Export và readability là hai điều kiện khác nhau. Nếu module đích không đọc module nguồn, cần sửa **requires** hoặc xem xét **--add-reads**.

**6. ALL-UNNAMED có bao gồm tất cả named module không?**

Không. Nó chỉ áp dụng cho unnamed module, thường là mã trên classpath. Named module phải được nêu đích danh.

## 16. Ghi nhớ

**--add-exports** tạo một export bổ sung có phạm vi xác định bởi module nguồn, package và module đích. Nó hữu ích cho biên dịch hoặc chạy ứng dụng cần truy cập package chưa được export, nhưng không sửa module descriptor, không bổ sung readability và không mở private member cho deep reflection.

Hãy dùng đúng target module, cấp quyền ở cả compile time và runtime khi cần, và ưu tiên API công khai thay cho phụ thuộc vào package nội bộ của JDK. Xem tùy chọn này như một biện pháp tương thích có thể gỡ bỏ khi ứng dụng đã chuyển sang API được hỗ trợ.

## Tài liệu tham khảo

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
