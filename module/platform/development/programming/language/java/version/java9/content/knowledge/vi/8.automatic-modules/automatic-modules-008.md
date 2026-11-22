# Chuyển dần một thư viện sang descriptor tường minh trong JPMS

## Mục tiêu

Một thư viện Java có thể được dùng trong hệ thống modular trước khi chính thư viện có tệp module descriptor. Khi JAR chưa có module-info.class nhưng được đặt trên module path, Java có thể xem nó là **automatic module**. Cách này hỗ trợ quá trình chuyển đổi từng bước.

Đích đến của bài là chuyển thư viện từ automatic module sang **explicit module** có module-info.java, đồng thời giữ ổn định tên mô-đun mà các ứng dụng đang dùng.

Sau bài này, bạn có thể:

- Nhận diện tên mô-đun của một JAR hiện tại.
- Giữ tên mô-đun ổn định bằng Automatic-Module-Name.
- Phân tích dependency và tạo bản nháp module descriptor.
- Thiết kế requires, exports, requires transitive, requires static, uses, provides và opens.
- Chuyển từ automatic module sang explicit module mà consumer không phải đổi tên dependency.
- Kiểm tra modular JAR và các ứng dụng phụ thuộc trước khi phát hành.

## 1. Automatic module là bước chuyển tiếp

JPMS được đưa vào Java 9. Một thư viện có thể chưa có module-info.java nhưng vẫn được dùng từ ứng dụng modular nếu JAR được đặt trên module path. Trong trường hợp đó, module finder có thể xem JAR là automatic module.

Automatic module có một số hành vi rộng để hỗ trợ chuyển đổi:

- Có tên mô-đun để consumer khai báo requires.
- Xuất tất cả package của JAR cho các mô-đun đọc nó.
- Có khả năng đọc các mô-đun khác theo quy tắc của automatic module.
- Chưa thể hiện một hợp đồng API được giới hạn rõ ràng bằng module descriptor.

Ví dụ, JAR của thư viện được phát hành mà không có module-info.class. Ứng dụng modular vẫn có thể khai báo:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

Nếu JAR được nhận diện là mô-đun com.acme.math, ứng dụng có thể import các kiểu public trong package của thư viện.

Đây là cơ chế tương thích hữu ích khi thư viện và các ứng dụng tiêu thụ chưa thể chuyển đổi cùng lúc. Tuy nhiên, một automatic module không thể hiện rõ package nào là API được hỗ trợ và package nào chỉ là implementation nội bộ. Bước chuyển sang explicit module giúp thư viện xác định hợp đồng đó.

## 2. Ổn định tên mô-đun trước khi phát hành descriptor

Tên mô-đun cần ổn định qua các phiên bản thư viện. Nếu JAR chưa có module descriptor và cũng không có tên tự khai báo, Java suy ra tên automatic module từ tên file JAR. Tên suy ra có thể thay đổi khi tên artifact hoặc phiên bản thay đổi.

Ví dụ, các tên file:

~~~text
acme-math-1.2.0.jar
acme-math-1.3.0.jar
~~~

có thể tạo ra tên automatic module khác nhau nếu tên mô-đun chỉ được suy ra từ tên file.

Để giữ tên cố định, thêm thuộc tính Automatic-Module-Name vào manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.math
~~~

Khi JAR được đặt trên module path, tên automatic module là com.acme.math. Các ứng dụng có thể khai báo requires com.acme.math mà không phụ thuộc vào tên file JAR.

Khi thư viện sau này có module-info.java, hãy giữ nguyên tên:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Tên trong descriptor tường minh phải giữ đúng định danh đã được công bố cho consumer. Không đổi tên mô-đun chỉ vì thư viện đã chuyển từ automatic sang explicit module.

## 3. Kiểm kê thư viện trước khi thêm module-info.java

Trước khi viết descriptor, cần xác định thư viện thực sự chứa những gì và đang phụ thuộc vào những mô-đun nào.

### Kiểm tra JAR hiện tại

Dùng:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

Với JAR chưa có descriptor nhưng có Automatic-Module-Name, kết quả sẽ cho biết nó là automatic module và hiển thị tên được nhận diện.

Nếu không có Automatic-Module-Name, hãy xác định tên automatic module được suy ra từ tên JAR. Nên công bố một tên ổn định trước khi các consumer phụ thuộc lâu dài vào tên suy ra.

### Phân tích dependency

Dùng jdeps để phân tích các lớp và dependency:

~~~bash
jdeps --multi-release 17 --recursive --summary libs/acme-math.jar
~~~

Có thể yêu cầu jdeps tạo bản nháp module-info.java:

~~~bash
jdeps --generate-module-info build/generated-module-info libs/acme-math.jar
~~~

Công cụ có thể đề xuất package exports và các requires dựa trên dependency mà nó phát hiện. Bản sinh ra chỉ là điểm khởi đầu: nó không biết đầy đủ ý định thiết kế API, package nào cần được giữ nội bộ, dependency nào là một phần của hợp đồng public, hay package nào chỉ được framework truy cập bằng reflection.

Vì vậy, hãy đọc và chỉnh sửa descriptor được đề xuất. Không đưa nguyên trạng mọi package được công cụ tìm thấy vào exports.

### Lập danh sách package và dependency

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Package API | Consumer có được phép import và sử dụng lâu dài không? |
| Package implementation | Có thể giữ nội bộ trong mô-đun không? |
| Dependency trực tiếp | Mã của thư viện có dùng kiểu từ dependency không? |
| Dependency trong chữ ký public | Consumer có cần đọc dependency để dùng API không? |
| Service provider | Thư viện có đăng ký implementation cho service không? |
| Reflection | Framework có cần truy cập sâu vào package hoặc thành viên không? |
| Split package | Package có bị chia giữa JAR hoặc mô-đun khác không? |

Kiểm tra dependency ở cả compile-time và runtime. Một thư viện có thể gọi trực tiếp dependency trong implementation mà không cần biến dependency đó thành một phần của API public.

## 4. Thiết kế module descriptor tường minh

Module descriptor là tệp module-info.java ở gốc source của mô-đun. Ví dụ tối thiểu:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Descriptor này nói rằng:

- Mô-đun có tên com.acme.math.
- Package com.acme.math.api là API được xuất.
- Những package khác không được xuất nếu không có chỉ thị tương ứng.
- java.base được yêu cầu ngầm định.

### requires: khai báo dependency

Nếu implementation của thư viện dùng một mô-đun khác, khai báo requires:

~~~java
module com.acme.math {
    requires com.acme.units;
    exports com.acme.math.api;
}
~~~

Tên trong requires là tên mô-đun, không phải tên JAR hoặc tên package. Dependency phải có mặt trên module path khi biên dịch và khi chạy theo đúng phạm vi sử dụng.

### requires transitive: dependency thuộc hợp đồng API

Dùng requires transitive khi kiểu từ dependency xuất hiện trong chữ ký API public và consumer cần đọc dependency đó để sử dụng API.

~~~java
module com.acme.math {
    requires transitive com.acme.units;
    exports com.acme.math.api;
}
~~~

Consumer chỉ cần requires com.acme.math nhưng cũng đọc được com.acme.units nhờ quan hệ transitive.

Không dùng transitive chỉ vì thư viện có dependency. Nếu dependency chỉ được gọi bên trong implementation và không xuất hiện trong hợp đồng API, requires thông thường phù hợp hơn.

### requires static: dependency chỉ cần ở compile-time

~~~java
module com.acme.math {
    requires static com.acme.annotations;
    exports com.acme.math.api;
}
~~~

requires static dành cho dependency cần khi biên dịch nhưng có thể tùy chọn lúc chạy, ví dụ annotation chỉ được xử lý trong quá trình build. Nếu logic runtime thật sự cần dependency, dependency vẫn phải có mặt khi chạy.

### exports: chỉ công khai package API

Automatic module xuất tất cả package. Khi chuyển sang explicit module, hãy chủ động chọn package cần công khai:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Package com.acme.math.internal không được xuất trong ví dụ này. Mô-đun khác đọc com.acme.math vẫn không thể dùng package nội bộ qua API modular thông thường.

Có thể dùng qualified exports khi package chỉ dành cho một số mô-đun cụ thể:

~~~java
module com.acme.math {
    exports com.acme.math.spi to com.acme.plugin;
}
~~~

Đây là cách công khai một SPI cho mô-đun đích đã chỉ định. Hãy dùng khi có ranh giới consumer rõ ràng.

### uses và provides: tích hợp ServiceLoader

Nếu thư viện sử dụng service, khai báo service contract:

~~~java
module com.acme.math {
    exports com.acme.math.spi;
    uses com.acme.math.spi.Strategy;
}
~~~

Nếu một mô-đun khác cung cấp implementation:

~~~java
module com.acme.math.fast {
    requires com.acme.math;
    provides com.acme.math.spi.Strategy
        with com.acme.math.fast.FastStrategy;
}
~~~

uses khai báo mô-đun tiêu thụ service; provides ... with ... khai báo implementation được cung cấp. Nếu consumer cần tự triển khai service, package chứa service interface phải được xuất. Khi chuyển sang explicit module, cần kiểm tra service provider metadata và module descriptor để service discovery tiếp tục hoạt động.

### opens: chỉ mở package cần reflection sâu

Automatic module cho phép truy cập rộng hơn. Explicit module mặc định đóng gói mạnh hơn. Nếu framework cần deep reflection vào package model, hãy mở đúng package cho mô-đun framework:

~~~java
module com.acme.math {
    exports com.acme.math.api;
    opens com.acme.math.model to com.acme.orm;
}
~~~

opens không thay thế exports. exports dành cho API truy cập thông thường; opens dành cho reflection sâu ở runtime. Chỉ mở package và mô-đun thực sự cần thiết, không mở toàn bộ mô-đun theo thói quen.

## 5. Vì sao chuyển sang explicit module có thể làm consumer lỗi?

Automatic module xuất mọi package. Khi chuyển sang explicit module, chỉ các package có exports mới được công khai.

Giả sử một consumer trước đây import:

~~~java
import com.acme.math.internal.FastCalculator;
~~~

Nếu package com.acme.math.internal không được xuất trong descriptor mới, consumer sẽ không còn truy cập được package đó qua JPMS, dù lớp FastCalculator vẫn là public.

Đây thường là dấu hiệu consumer đang phụ thuộc vào implementation detail. Trước khi phát hành descriptor:

1. Tìm các package mà consumer thực tế import.
2. Phân loại package thành API được hỗ trợ và implementation nội bộ.
3. Nếu consumer cần chức năng đó lâu dài, thiết kế API public ổn định thay vì xuất toàn bộ nội bộ.
4. Nếu một package cần được công khai cho một plugin cụ thể, cân nhắc qualified exports.
5. Kiểm thử các consumer đại diện trên module path với descriptor mới.

Một thay đổi descriptor có thể làm lộ dependency ẩn mà trước đây automatic module cho phép. Hãy xử lý như một thay đổi hợp đồng API và kiểm thử trước khi phát hành.

## 6. Quy trình chuyển đổi từng giai đoạn

### Giai đoạn 1: Công bố tên automatic module ổn định

Nếu thư viện chưa có tên mô-đun ổn định, thêm Automatic-Module-Name vào manifest. Phát hành một phiên bản trung gian để consumer có thể chuyển sang requires theo tên ổn định.

Ví dụ:

~~~text
Automatic-Module-Name: com.acme.math
~~~

Ở giai đoạn này, thư viện vẫn có thể chưa chứa module-info.class. Consumer modular dùng tên com.acme.math như một automatic module.

### Giai đoạn 2: Kiểm kê dependency và package

- Dùng jar --describe-module để xác nhận tên mô-đun.
- Dùng jdeps để phân tích dependency.
- Xác định package API, package nội bộ, service và yêu cầu reflection.
- Kiểm tra split package và dependency trùng tên mô-đun trên module path.
- Ghi nhận các consumer đang sử dụng package nội bộ.

Có thể dùng jdeps --generate-module-info để tạo bản nháp, nhưng cần review thủ công.

### Giai đoạn 3: Viết module-info.java

Giữ nguyên tên com.acme.math. Thêm các requires cần thiết, exports package API, uses/provides cho service và opens có phạm vi hẹp cho framework.

Ví dụ:

~~~java
module com.acme.math {
    requires com.acme.units;
    exports com.acme.math.api;
    exports com.acme.math.spi;
    uses com.acme.math.spi.Strategy;
}
~~~

Descriptor trên là minh họa. Chỉ giữ các chỉ thị thực sự phù hợp với dependency và hợp đồng của thư viện.

### Giai đoạn 4: Biên dịch và đóng gói explicit module

Biên dịch thư viện với JDK mục tiêu:

~~~bash
javac --release 17 -d out src/module-info.java src/com/acme/math/api/Calculator.java
~~~

Với dự án nhiều package hoặc nhiều source file, cấu hình source path/module source path hoặc dùng build tool để biên dịch đầy đủ. Đóng gói:

~~~bash
jar --create --file build/libs/com.acme.math.jar -C out .
~~~

Kiểm tra descriptor đã đóng gói:

~~~bash
jar --describe-module --file build/libs/com.acme.math.jar
~~~

Kết quả cần cho thấy tên com.acme.math và các package exports dự kiến. Nếu kết quả vẫn nhận diện JAR là automatic module, hãy kiểm tra module-info.class có nằm ở gốc JAR hay không.

### Giai đoạn 5: Kiểm thử consumer không đổi tên dependency

Một consumer modular đã khai báo:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

Giữ nguyên module descriptor của consumer, thay JAR automatic bằng JAR explicit và chạy lại:

~~~bash
javac --release 17 --module-path libs -d app-out --module-source-path app-src -m com.acme.app
java --module-path "libs;app-out" -m com.acme.app/com.acme.app.Main
~~~

Consumer vẫn yêu cầu com.acme.math. Nếu package API và dependency contract được giữ đúng, mã nguồn consumer có thể tiếp tục biên dịch và chạy.

### Giai đoạn 6: Kiểm tra dependency và hành vi thực tế

- Chạy jdeps --check trên mô-đun đã đóng gói.
- Kiểm tra module path triển khai bằng java --validate-modules.
- Chạy test của thư viện và consumer.
- Kiểm thử ServiceLoader nếu có uses/provides.
- Kiểm thử framework dùng reflection nếu có opens.
- Kiểm tra ứng dụng khi chạy bằng module path thực tế.
- Kiểm tra dependency tree của build để tránh kéo nhiều phiên bản hoặc tên mô-đun trùng nhau.

Chỉ phát hành khi descriptor, artifact và consumer tests nhất quán.

## 7. Ví dụ chạy được: automatic module sang explicit module

Ví dụ sau mô phỏng hai phiên bản của cùng một thư viện. Ứng dụng consumer giữ nguyên module descriptor và mã nguồn; chỉ thay artifact của thư viện.

### Mã nguồn thư viện

Tệp com/acme/math/api/Calculator.java:

~~~java
package com.acme.math.api;

public final class Calculator {
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

Ở phiên bản đầu, thư viện chưa có module-info.java. Manifest của JAR chứa:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.math
~~~

Biên dịch lớp thư viện:

~~~bash
javac --release 17 -d auto-classes src/com/acme/math/api/Calculator.java
~~~

Đóng gói JAR automatic bằng manifest có thuộc tính Automatic-Module-Name:

~~~bash
jar --create --file com.acme.math-auto.jar --manifest MANIFEST.MF -C auto-classes .
~~~

### Mã nguồn consumer

Tệp app-src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

Tệp app-src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.math.api.Calculator;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Calculator().add(20, 22));
    }
}
~~~

Biên dịch và chạy consumer với automatic module:

~~~bash
javac --release 17 --module-path com.acme.math-auto.jar -d app-out --module-source-path app-src -m com.acme.app
java --module-path "com.acme.math-auto.jar;app-out" -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
42
~~~

### Thêm descriptor tường minh cho cùng thư viện

Tệp module-info.java mới:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Biên dịch thư viện:

~~~bash
javac --release 17 -d explicit-classes src/module-info.java src/com/acme/math/api/Calculator.java
~~~

Đóng gói:

~~~bash
jar --create --file com.acme.math-explicit.jar -C explicit-classes .
~~~

Kiểm tra:

~~~bash
jar --describe-module --file com.acme.math-explicit.jar
~~~

Kết quả quan trọng:

~~~text
com.acme.math
exports com.acme.math.api
requires java.base mandated
~~~

Dùng JAR explicit thay cho JAR automatic, giữ nguyên mã nguồn consumer:

~~~bash
javac --release 17 --module-path com.acme.math-explicit.jar -d app-out --module-source-path app-src -m com.acme.app
java --module-path "com.acme.math-explicit.jar;app-out" -m com.acme.app/com.acme.app.Main
~~~

Stdout vẫn là:

~~~text
42
~~~

Ví dụ đã được biên dịch bằng javac --release 17 và chạy trên JDK 24. Cả hai giai đoạn đều in 42. Tên mô-đun com.acme.math và mã nguồn consumer không thay đổi; khác biệt là JAR thứ hai chứa module descriptor tường minh.

## 8. Kiểm tra descriptor sau khi chuyển đổi

Các lệnh sau hữu ích trong pipeline:

~~~bash
jar --describe-module --file build/libs/com.acme.math.jar
jdeps --module-path build/libs --check com.acme.math
java --validate-modules --module-path build/mods
~~~

- jar --describe-module xác nhận tên, exports, requires, uses/provides và main class metadata nếu có.
- jdeps --check kiểm tra tính nhất quán dependency của descriptor và đưa ra đồ thị dependency.
- java --validate-modules kiểm tra các mô-đun được tìm thấy trên module path, bao gồm các vấn đề như split package.

Ngoài các lệnh này, hãy biên dịch và chạy ít nhất một consumer thật. Descriptor có thể hợp lệ về mặt cú pháp nhưng vẫn thiếu exports, requires hoặc opens mà hệ sinh thái consumer đang cần.

## 9. Các lỗi thường gặp khi chuyển đổi

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Consumer báo không tìm thấy mô-đun | Tên trong requires khác tên JAR/module descriptor hoặc module path thiếu artifact | Dùng jar --describe-module và kiểm tra module path |
| Consumer không truy cập được package trước đây dùng được | Explicit module chưa exports package đó | Xác định package là API hay implementation; chỉ xuất API được hỗ trợ |
| Consumer không đọc được kiểu trong chữ ký public | Thiếu requires transitive ở mô-đun cung cấp API | Chỉ thêm transitive khi dependency thực sự thuộc hợp đồng API |
| Framework không truy cập được field private | Thiếu opens cho package cần reflection | Mở đúng package cho đúng mô-đun framework |
| ServiceLoader không tìm thấy implementation | Thiếu uses/provides hoặc provider metadata không khớp | Kiểm tra service contract và khai báo service |
| Module resolver báo split package | Package bị chia giữa nhiều named module | Gom package về một mô-đun hoặc thiết kế lại namespace |
| Tên mô-đun thay đổi theo tên JAR | Trước đó tên automatic module được suy ra từ tên file | Công bố Automatic-Module-Name ổn định và giữ tên đó trong descriptor |
| jdeps đề xuất descriptor quá rộng | Công cụ chỉ suy luận từ dependency, không biết hợp đồng API | Review exports/requires thủ công |

## 10. Nguyên tắc phát hành thư viện modular

- Giữ nguyên module name đã công bố cho consumer khi chuyển từ automatic sang explicit module.
- Chỉ xuất package thuộc API được hỗ trợ.
- Khai báo dependency đúng với vai trò của nó: requires, requires transitive hoặc requires static.
- Khai báo uses/provides cho service nếu thư viện sử dụng cơ chế service.
- Mở reflection bằng opens có phạm vi hẹp khi framework thực sự cần.
- Không để package bị chia giữa các named module trong cùng module layer.
- Kiểm tra JAR sau đóng gói, không chỉ kiểm tra source descriptor.
- Biên dịch và chạy consumer đại diện với JAR explicit mới.
- Kiểm tra runtime dependency graph và module path giống môi trường triển khai.

## Kết luận

Chuyển một thư viện sang explicit module nên là một thay đổi có kiểm soát về hợp đồng mô-đun. Hãy ổn định tên bằng Automatic-Module-Name, kiểm kê dependency và package, thiết kế module-info.java với exports/requires phù hợp, rồi kiểm thử consumer trước và sau khi thay artifact.

Điểm xác nhận quan trọng là tên mô-đun không đổi và consumer vẫn biên dịch, chạy được với descriptor mới. Khi đó thư viện đã chuyển từ automatic module sang explicit module, có API được công khai rõ ràng và ranh giới implementation được kiểm soát tốt hơn trong Java hiện đại.
