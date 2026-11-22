# Chọn module bằng --add-modules

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của tùy chọn --add-modules trong JPMS, phân biệt module path với tập module được phân giải, sử dụng các giá trị ALL-DEFAULT, ALL-SYSTEM và ALL-MODULE-PATH, đồng thời áp dụng tùy chọn này khi biên dịch, chạy ứng dụng và tạo runtime image bằng jlink.

## 1. --add-modules dùng để làm gì?

Trong Java Platform Module System (JPMS), Java không tự động đưa mọi module có thể tìm thấy vào runtime. Hệ thống bắt đầu từ một tập module gốc (root modules), sau đó phân giải các dependency được khai báo bằng requires để tạo module graph.

Tùy chọn --add-modules cho phép bổ sung một hoặc nhiều module vào tập root modules ban đầu. Khi một module được thêm làm root, module đó được đưa vào quá trình phân giải cùng các dependency mà nó yêu cầu.

Cú pháp tổng quát:

~~~bash
--add-modules module-name[,module-name...]
~~~

Ví dụ:

~~~bash
java --add-modules java.sql -cp app.jar com.acme.Main
~~~

Lệnh trên yêu cầu launcher đưa module java.sql vào tập root modules khi khởi động ứng dụng. Nếu module này yêu cầu các module khác, các dependency đó cũng được phân giải theo module graph.

Điều cần nhớ là --add-modules chọn module cần được phân giải. Nó không tự động thêm package vào exports, không tạo quan hệ đọc giữa hai named module và cũng không tải hoặc khởi tạo mọi class trong module ngay lập tức.

## 2. Module path và root modules khác nhau thế nào?

Hai khái niệm này thường bị nhầm:

- Module path là nơi công cụ tìm các module có thể quan sát được. Nó có thể chứa modular JAR, exploded module và automatic module.
- Root modules là các module được chọn làm điểm bắt đầu để phân giải module graph.
- Dependency graph được hình thành từ các root và những module mà chúng yêu cầu.

Ví dụ, thư mục mods có ba JAR:

~~~text
mods/
  com.acme.app.jar
  com.acme.logging.jar
  com.acme.metrics.jar
~~~

Module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.logging;
}
~~~

Khi chạy:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Launcher phân giải com.acme.app và dependency com.acme.logging. Module com.acme.metrics có mặt trên module path nhưng không tự động được phân giải chỉ vì JAR của nó tồn tại ở đó.

Nếu muốn thêm metrics như một root module độc lập, có thể chạy:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics \
     --module com.acme.app/com.acme.app.Main
~~~

Lúc này com.acme.metrics được thêm vào module graph cùng ứng dụng và các dependency của nó. Tuy nhiên, nếu mã trong com.acme.app cần truy cập trực tiếp kiểu public của com.acme.metrics, ứng dụng vẫn phải có quan hệ đọc phù hợp, thường được khai báo bằng requires trong module-info.java.

## 3. --add-modules không thay thế requires

Giả sử module ứng dụng muốn gọi trực tiếp API của module thư viện:

~~~java
package com.acme.app;

import com.acme.metrics.Counter;

public class Main {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
    }
}
~~~

Module descriptor cần khai báo dependency:

~~~java
module com.acme.app {
    requires com.acme.metrics;
}
~~~

Khai báo requires vừa tạo dependency trong module graph, vừa thiết lập quan hệ readability giữa module ứng dụng và module metrics.

Nếu chỉ chạy với:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics \
     --module com.acme.app/com.acme.app.Main
~~~

thì com.acme.metrics được phân giải, nhưng điều đó không tự tạo readability edge từ com.acme.app tới com.acme.metrics. Nếu source cần tham chiếu kiểu của metrics, hãy khai báo requires.

Có thể tóm tắt:

| Cơ chế | Tác dụng |
|---|---|
| --module-path | Tìm vị trí các module |
| --add-modules | Bổ sung module vào tập root để phân giải |
| requires | Khai báo dependency và quan hệ đọc giữa named modules |
| --add-reads | Thêm quan hệ đọc ở thời điểm chạy hoặc biên dịch theo cấu hình công cụ |
| exports | Cho phép module khác truy cập các kiểu public trong package |
| --add-exports | Mở quyền truy cập một package cho module đích qua tùy chọn công cụ |

Vì vậy, khi lỗi là module không được phân giải, hãy kiểm tra module path và root modules. Khi lỗi là module không đọc được package hoặc kiểu, hãy kiểm tra requires, exports hoặc tùy chọn truy cập tương ứng.

## 4. Các giá trị đặc biệt của --add-modules

Ngoài tên module cụ thể, tùy chọn này hỗ trợ một số giá trị đặc biệt:

| Giá trị | Ý nghĩa |
|---|---|
| ALL-DEFAULT | Bổ sung toàn bộ các default root modules |
| ALL-SYSTEM | Bổ sung tất cả system modules có thể quan sát được |
| ALL-MODULE-PATH | Bổ sung tất cả module có thể quan sát được trên module path |

Ví dụ:

~~~bash
java --add-modules ALL-DEFAULT -cp app.jar com.acme.Main
~~~

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --module com.acme.app/com.acme.app.Main
~~~

~~~bash
java --add-modules ALL-SYSTEM -cp app.jar com.acme.Main
~~~

Một số lưu ý:

- ALL-DEFAULT dùng tập root mặc định của công cụ trong cấu hình hiện tại.
- ALL-SYSTEM có thể làm module graph chứa nhiều module nền tảng hơn mức ứng dụng cần.
- ALL-MODULE-PATH có thể kéo tất cả module quan sát được từ module path vào graph, kể cả các module không cần thiết cho chức năng chính.
- Các giá trị đặc biệt được viết đúng chữ hoa và dùng như một phần tử trong danh sách module phân tách bằng dấu phẩy.

Không nên chọn ALL-MODULE-PATH chỉ vì muốn chắc chắn module cần thiết được tìm thấy. Trong build và runtime có kiểm soát, khai báo rõ tên module cần thêm thường giúp đồ thị module dễ hiểu và gọn hơn.

## 5. Dùng --add-modules với java launcher

Khi chạy ứng dụng trên classpath, --add-modules có thể bổ sung một system module mà ứng dụng cần sử dụng. Ví dụ, một chương trình dùng Vector API của JDK:

~~~java
import jdk.incubator.vector.IntVector;

public class VectorDemo {
    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4};
        IntVector vector = IntVector.fromArray(
            IntVector.SPECIES_128,
            values,
            0
        );
        System.out.println(vector);
    }
}
~~~

Biên dịch:

~~~bash
javac --add-modules jdk.incubator.vector VectorDemo.java
~~~

Chạy:

~~~bash
java --add-modules jdk.incubator.vector VectorDemo
~~~

Module jdk.incubator.vector là incubator module nên cần được thêm rõ ràng trong các lệnh sử dụng API này. Tùy chọn phải được áp dụng ở cả bước biên dịch và bước chạy để module có mặt trong module graph của từng tiến trình.

Ví dụ trên dùng unnamed module vì source được biên dịch và chạy theo classpath mặc định. Với ứng dụng modular, cần thêm quan hệ requires phù hợp trong module descriptor nếu mã nguồn tham chiếu trực tiếp API của module đó.

## 6. Dùng --add-modules khi biên dịch bằng javac

Javac cũng hỗ trợ --add-modules để bổ sung module vào tập root khi phân giải các module phục vụ biên dịch.

Ví dụ:

~~~bash
javac \
    --module-path mods \
    --add-modules com.acme.annotation.api \
    -d out \
    src/com/acme.tool/com.acme.tool/module-info.java \
    src/com.acme.tool/com.acme.tool/Main.java
~~~

Trong ví dụ, module com.acme.annotation.api nằm trên module path và được thêm vào tập root. Module nguồn đang biên dịch vẫn cần khai báo requires nếu nó trực tiếp đọc API của module đó.

Với source theo module, có thể dùng module source path:

~~~bash
javac \
    --module-source-path src \
    --module-path mods \
    --add-modules com.acme.annotation.api \
    -d out \
    -m com.acme.tool
~~~

Các điểm cần phân biệt:

- --module-source-path chỉ vị trí mã nguồn của các module đang biên dịch.
- --module-path chỉ vị trí các module dependency đã được biên dịch hoặc đóng gói.
- --add-modules bổ sung root modules cho quá trình phân giải.
- -m hoặc --module chọn module nguồn cần biên dịch.

Nếu module dependency đã được kéo vào graph qua requires của module nguồn, việc thêm nó một lần nữa bằng --add-modules thường không cần thiết. Tùy chọn này hữu ích khi cần đưa thêm module độc lập vào graph hoặc khi công cụ cần quan sát module đó trong quá trình biên dịch.

## 7. Dùng --add-modules với jlink

jlink tạo runtime image tùy chỉnh từ một tập module gốc và các dependency của chúng. Tùy chọn --add-modules của jlink xác định các root modules cần đưa vào image.

Ví dụ, ứng dụng có module com.acme.app và phụ thuộc vào java.sql:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --output runtime-image
~~~

jlink phân giải module com.acme.app và các dependency cần thiết, sau đó tạo runtime image tại runtime-image.

Có thể thêm nhiều root module:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app,com.acme.admin \
    --output runtime-image
~~~

Hoặc thêm mọi module quan sát được trên module path:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules ALL-MODULE-PATH \
    --output runtime-image
~~~

Lựa chọn ALL-MODULE-PATH có thể tạo image lớn hơn đáng kể, vì nhiều module không liên quan cũng được đưa vào graph. Khi tạo runtime image cho sản phẩm, nên bắt đầu từ module ứng dụng và các root module thực sự cần thiết.

Sau khi tạo image, có thể chạy ứng dụng bằng launcher trong image:

~~~bash
runtime-image/bin/java \
    --module com.acme.app/com.acme.app.Main
~~~

Trên Windows, launcher nằm ở runtime-image\\bin\\java.exe.

## 8. Phân biệt --add-modules với --bind-services

Khi đóng gói ứng dụng modular, đặc biệt ứng dụng sử dụng ServiceLoader, cần phân biệt việc thêm module gốc với việc liên kết service provider.

- --add-modules chỉ định các root module cần phân giải.
- --bind-services yêu cầu jlink liên kết các service provider cho các service được sử dụng trong module graph, đưa provider module phù hợp vào runtime image.

Ví dụ:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --bind-services \
    --output runtime-image
~~~

Giả sử com.acme.app khai báo uses com.acme.spi.Formatter và một module khác khai báo provides com.acme.spi.Formatter with com.acme.impl.HtmlFormatter. Với --bind-services, jlink có thể tìm và liên kết provider phù hợp trong tập module quan sát được.

Nếu biết chính xác provider module và muốn đưa nó vào image như một root độc lập, có thể nêu tên provider trong --add-modules. --bind-services hữu ích khi muốn jlink tự xử lý quan hệ service dựa trên uses/provides.

Điều kiện quan trọng vẫn là các module provider phải có thể quan sát được trên module path, có descriptor hợp lệ và khai báo provides đúng service type.

## 9. Kết hợp với --limit-modules

--limit-modules giới hạn tập module mà công cụ có thể quan sát khi phân giải module graph. Nó thường được dùng để mô phỏng một môi trường runtime nhỏ hơn hoặc giới hạn các module được phép tham gia phân giải.

Ví dụ:

~~~bash
java \
    --module-path mods \
    --limit-modules java.base,java.logging,com.acme.app \
    --add-modules com.acme.app \
    --module com.acme.app/com.acme.app.Main
~~~

Trong trường hợp này, tập module quan sát được bị giới hạn theo danh sách được nêu. Nếu dependency cần thiết không nằm trong tập có thể quan sát, quá trình phân giải sẽ thất bại.

Hai tùy chọn có vai trò khác nhau:

| Tùy chọn | Vai trò |
|---|---|
| --limit-modules | Giới hạn module nào có thể được quan sát và tham gia phân giải |
| --add-modules | Chọn module gốc từ tập module có thể quan sát |

Nếu một module được thêm bằng --add-modules nhưng không thể quan sát được do giới hạn module, công cụ không thể phân giải nó. Vì vậy cần kiểm tra cả hai tùy chọn khi xử lý lỗi module not found.

## 10. Khi nào nên dùng tên module cụ thể và khi nào dùng ALL-*

Ưu tiên tên module cụ thể khi:

- Ứng dụng cần một module JDK tùy chọn hoặc incubator module.
- Cần thêm một module độc lập vào graph mà không muốn đưa toàn bộ module path vào.
- Đang tạo runtime image có kích thước cần kiểm soát.
- Muốn lệnh build dễ đọc và có thể tái lập giữa các môi trường.

Dùng ALL-DEFAULT khi cần bổ sung tập root mặc định theo chính sách của công cụ. Dùng ALL-SYSTEM khi có chủ đích đưa toàn bộ system modules có thể quan sát vào graph. Dùng ALL-MODULE-PATH khi muốn tất cả module trên module path đều tham gia phân giải, chẳng hạn một môi trường thử nghiệm hoặc image tổng hợp.

Không nên dùng các giá trị ALL-* như biện pháp sửa lỗi chung. Chúng có thể che khuất dependency chưa khai báo, khiến module graph phình to và làm runtime image lớn hơn.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| FindException: Module ... not found | Tên module sai hoặc module không nằm trên module path | Kiểm tra tên bằng jar --describe-module và kiểm tra --module-path |
| Module có trên module path nhưng không được phân giải | Module không phải root và không phải dependency của root nào | Thêm tên module vào --add-modules hoặc khai báo requires nếu là dependency trực tiếp |
| Module đã được phân giải nhưng ứng dụng không truy cập được API | Chưa có quan hệ readability hoặc package chưa export | Khai báo requires, kiểm tra exports; chỉ dùng --add-reads/--add-exports khi thật sự cần |
| javac không tìm thấy module khi biên dịch | Module path sai hoặc module bị giới hạn bởi --limit-modules | Kiểm tra module path và tập module có thể quan sát |
| Runtime image thiếu provider | Chưa liên kết service provider hoặc provider không thể quan sát | Kiểm tra uses/provides, module path và cân nhắc --bind-services hoặc thêm provider vào --add-modules |
| Runtime image quá lớn | Dùng ALL-SYSTEM hoặc ALL-MODULE-PATH không cần thiết | Chỉ chọn root modules ứng dụng thực sự cần |
| Incubator API không khả dụng | Chưa thêm incubator module ở bước compile hoặc runtime | Thêm module tương ứng bằng --add-modules ở cả hai bước |

Khi gặp lỗi, hãy xác định lỗi thuộc một trong ba lớp: module không thể tìm thấy, module không được phân giải, hay module đã phân giải nhưng không có quyền truy cập API. Ba trường hợp này cần cách xử lý khác nhau.

## Ghi nhớ

--add-modules bổ sung module vào tập root modules để JPMS phân giải module graph. --module-path chỉ nơi tìm module; requires khai báo dependency và readability giữa named modules; exports điều khiển package nào được truy cập. Các giá trị ALL-DEFAULT, ALL-SYSTEM và ALL-MODULE-PATH lần lượt chọn tập root mặc định, tất cả system modules có thể quan sát và tất cả module trên module path. Khi dùng jlink, --add-modules chọn module gốc cho runtime image, còn --bind-services xử lý việc liên kết service provider.