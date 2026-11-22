# javac --module-path và --add-modules

## 1. Vì sao javac cần module path?

Khi biên dịch một ứng dụng Java dùng Java Platform Module System (JPMS), trình biên dịch **javac** phải tìm được các module mà mã nguồn phụ thuộc. Tùy chọn **--module-path** chỉ định nơi chứa các module đó.

Module path có thể chứa:

- Modular JAR có file **module-info.class**.
- Thư mục module đã biên dịch dạng exploded module.
- Automatic module, tức JAR chưa có module descriptor nhưng được nhận diện như module tự động khi đặt trên module path.

Ví dụ, một thư mục **lib** chứa JAR **com.example.codec.jar**. Module ứng dụng khai báo:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

Có thể biên dịch module ứng dụng bằng:

~~~bash
javac --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Trong lệnh này:

- **--module-path lib** (viết tắt **-p lib**) giúp javac tìm module phụ thuộc trong thư mục lib.
- **--module-source-path src** chỉ định cấu trúc thư mục chứa mã nguồn của các module.
- **-d out** chỉ định nơi ghi file class và module descriptor đã biên dịch.
- **-m com.example.app** chọn module cần biên dịch.

Nếu module phụ thuộc nằm ở nơi khác, hãy đưa các vị trí đó vào module path. Trình biên dịch cần phân giải được các module được khai báo trong **requires** của module đang biên dịch.

## 2. Phân biệt module path và classpath

**Classpath** chứa các class và JAR được nạp vào unnamed module. **Module path** chứa các module có thể được hệ thống JPMS nhận diện và phân giải theo tên module.

| Tùy chọn | Mục đích | Cách tổ chức |
|---|---|---|
| **--class-path** hoặc **-cp** | Tìm class và JAR trên classpath | Các class thuộc unnamed module |
| **--module-path** hoặc **-p** | Tìm named module và automatic module | Module descriptor, tên module và module graph |
| **--module-source-path** | Tìm mã nguồn của nhiều module | Thư mục mã nguồn được tổ chức theo tên module |

Ví dụ biên dịch một chương trình classpath thông thường:

~~~bash
javac -cp "lib/*" -d out src/com/example/Main.java
~~~

Ví dụ biên dịch named module có phụ thuộc nằm trong module path:

~~~bash
javac -p lib -d out --module-source-path src -m com.example.app
~~~

Không nên đặt một thư viện lên classpath chỉ để tránh khai báo module. Nếu ứng dụng đã dùng named module và thư viện có thể được dùng như module, hãy đưa thư viện vào module path rồi khai báo **requires** phù hợp.

Một thư viện JAR có thể là modular JAR hoặc automatic module. Có thể kiểm tra cách JDK nhận diện module bằng:

~~~bash
jar --describe-module --file lib/com.example.codec.jar
~~~

Nếu JAR có module descriptor, tên module được lấy từ descriptor. Nếu không có descriptor, tên automatic module được suy ra từ metadata hoặc tên file JAR, trừ khi manifest khai báo **Automatic-Module-Name**. Nên dùng tên module ổn định được thư viện công bố thay vì tự suy đoán từ tên file.

## 3. Cấu trúc mã nguồn nhiều module

Khi biên dịch nhiều module từ source tree, mỗi module thường nằm trong thư mục riêng cùng tên module:

~~~text
project/
  src/
    com.example.model/
      module-info.java
      com/example/model/Customer.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  lib/
    com.example.codec.jar
  out/
~~~

Module model:

~~~java
module com.example.model {
    exports com.example.model;
}
~~~

Class trong module model:

~~~java
package com.example.model;

public record Customer(String name) {}
~~~

Module ứng dụng:

~~~java
module com.example.app {
    requires com.example.model;
    requires com.example.codec;
}
~~~

Class khởi chạy:

~~~java
package com.example.app;

import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Lan");
        System.out.println(customer.name());
    }
}
~~~

Nếu **com.example.codec** là một thư viện ngoài đã đóng gói thành JAR, thư mục **lib** phải có JAR đó và module descriptor của nó phải khai báo package cần dùng bằng **exports**.

Có thể biên dịch đồng thời các module nguồn bằng:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.model,com.example.app
~~~

Lệnh này chọn hai module nguồn để biên dịch. javac đọc module descriptor, kiểm tra các quan hệ **requires**, tìm các module phụ thuộc trong module source path và module path, rồi ghi kết quả vào **out**.

Nếu các module nguồn phụ thuộc lẫn nhau theo quan hệ hợp lệ, hãy đưa chúng vào cùng lượt biên dịch hoặc biên dịch theo thứ tự phụ thuộc. Không thể giải quyết một vòng phụ thuộc module không hợp lệ chỉ bằng cách thêm tên module vào dòng lệnh.

Sau khi biên dịch, thư mục output có cấu trúc tương tự:

~~~text
out/
  com.example.model/
    module-info.class
    com/example/model/Customer.class
  com.example.app/
    module-info.class
    com/example/app/Main.class
~~~

Đây là các exploded module. Có thể dùng trực tiếp thư mục **out** làm module path khi chạy ứng dụng:

~~~bash
java --module-path out:lib \
     -m com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách giữa các phần tử module path là dấu chấm phẩy:

~~~powershell
java --module-path "out;lib" -m com.example.app/com.example.app.Main
~~~

## 4. Dùng --module-path trong các tình huống phổ biến

### Biên dịch một module phụ thuộc vào JAR bên ngoài

Giả sử source tree chỉ chứa **com.example.app**, còn thư viện **com.example.codec** đã được đóng gói trong **lib**:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

Trong **module-info.java** của ứng dụng:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

javac tìm module **com.example.codec** trên module path, kiểm tra package được xuất và cho phép mã nguồn sử dụng các kiểu public mà module đó công khai.

### Biên dịch một module nguồn không có source tree nhiều module

Nếu chỉ có một module và muốn chỉ định trực tiếp các file nguồn, có thể truyền file **module-info.java** cùng các file Java:

~~~bash
javac --module-path lib \
      -d out \
      src/module-info.java \
      src/com/example/app/Main.java
~~~

Cách này phù hợp với source tree đơn giản. Với dự án nhiều module, **--module-source-path** và **-m** giúp chọn module rõ ràng và dễ mở rộng hơn.

### Dùng module path cùng classpath

Trong một dự án chuyển đổi dần sang JPMS, một số thư viện có thể vẫn ở classpath trong khi các named module đã được biên dịch trên module path. Khi đó, có thể dùng đồng thời **--class-path** và **--module-path**:

~~~bash
javac \
  --module-path mods \
  --class-path "legacy-libs/*" \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

Cần kiểm tra chính xác thư viện nào là named module và thư viện nào được sử dụng như classpath. Không đưa cùng một thư viện vào cả hai vị trí vì có thể tạo ra tình trạng trùng class hoặc xung đột khi phân giải.

## 5. --add-modules có ý nghĩa gì?

Tùy chọn **--add-modules** yêu cầu javac đưa thêm một hoặc nhiều module vào tập module gốc cần phân giải:

~~~bash
javac --module-path lib \
      --add-modules com.example.codec \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

Tùy chọn này hữu ích khi biên dịch mã thuộc unnamed module nhưng cần nhìn thấy một named module trên module path, hoặc khi cần đưa module bổ sung vào module graph để phân giải trong quá trình biên dịch.

Có thể chỉ định nhiều module, phân tách bằng dấu phẩy:

~~~bash
javac --module-path lib \
      --add-modules com.example.codec,com.example.json \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

Ngoài tên module cụ thể, có thể dùng các giá trị đặc biệt:

- **ALL-MODULE-PATH**: thêm tất cả module quan sát được trên module path vào tập module cần phân giải.
- **ALL-SYSTEM**: thêm tất cả module hệ thống vào tập module cần phân giải.

Ví dụ:

~~~bash
javac --module-path lib \
      --add-modules ALL-MODULE-PATH \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

Dùng **ALL-MODULE-PATH** có thể thuận tiện khi đang khảo sát hoặc tích hợp nhiều module, nhưng nó làm phạm vi phân giải rộng hơn. Với build ổn định, ưu tiên liệt kê module cụ thể để kết quả dễ kiểm soát.

## 6. --add-modules không thay thế requires

Đây là điểm cần nhớ khi biên dịch named module.

Giả sử module ứng dụng có mã:

~~~java
package com.example.app;

import com.example.codec.Encoder;

public class Main {
    public static void main(String[] args) {
        Encoder encoder = new Encoder();
        System.out.println(encoder.encode("hello"));
    }
}
~~~

Nếu mã này thuộc named module **com.example.app**, module descriptor vẫn phải khai báo:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

Đặt **--add-modules com.example.codec** trên dòng lệnh không tự sửa **module-info.java**, không tạo quan hệ readability thay cho **requires**, và không tự xuất package từ module phụ thuộc.

Vai trò của hai phần khác nhau:

- **requires** là hợp đồng phụ thuộc được ghi trong module descriptor và đi cùng module khi phân phối.
- **--add-modules** điều chỉnh tập module gốc được đưa vào quá trình phân giải của lệnh javac.

Vì vậy, khi mã nguồn của named module trực tiếp import kiểu từ module khác, hãy khai báo **requires**. Chỉ dùng **--add-modules** cho nhu cầu mở rộng tập module được phân giải ngoài các module gốc mặc định.

Với mã thuộc unnamed module trên classpath, quy tắc khác: unnamed module có thể đọc các named module đã được phân giải. Khi đó, **--module-path** cung cấp module và **--add-modules** có thể làm cho module được đưa vào graph để mã classpath sử dụng API public đã export.

## 7. Phân biệt -m và --add-modules

Hai tùy chọn có tên gần nhau nhưng nhiệm vụ khác nhau:

| Tùy chọn | Ý nghĩa |
|---|---|
| **-m** hoặc **--module** | Chỉ định module nguồn cần biên dịch |
| **--add-modules** | Thêm module vào tập module gốc cần phân giải |

Ví dụ:

~~~bash
javac --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Lệnh trên chọn **com.example.app** để biên dịch.

Trong khi đó:

~~~bash
javac --module-path lib \
      --add-modules com.example.tools \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Lệnh thứ hai vẫn biên dịch **com.example.app**, đồng thời yêu cầu phân giải thêm **com.example.tools**. Nếu mã trong named module cần đọc và sử dụng API của tools, descriptor vẫn phải có khai báo phù hợp, thường là **requires com.example.tools**.

Không nhầm **-m** của javac với **-m** của java trong mọi ngữ cảnh. Khi dùng javac, **-m** chọn module cần biên dịch; khi dùng java, **-m** chọn module cần khởi chạy.

## 8. Khi nào cần --add-modules?

Một số tình huống có thể cần thêm module vào tập phân giải:

1. **Ứng dụng classpath dùng API từ named module:** chỉ định module trên module path và thêm module đó bằng **--add-modules** để compiler nhận diện module.
2. **Phụ thuộc được chọn động:** tên module được lấy từ cấu hình hoặc cơ chế plugin nên không xuất hiện trong quan hệ requires tĩnh.
3. **Khảo sát module graph:** dùng **ALL-MODULE-PATH** để xem xét các module có trên module path.
4. **Build cần module hệ thống bổ sung:** chỉ định module JDK cụ thể khi yêu cầu công cụ biên dịch phân giải module đó.

Nếu một named module trực tiếp sử dụng API của module khác, khai báo **requires** vẫn là cách mô tả đúng phụ thuộc. Nếu module cần được đọc động mà không thể khai báo trong descriptor, còn có tùy chọn **--add-reads** trong các công cụ hỗ trợ JPMS; đây là một cơ chế riêng và cần cân nhắc kỹ vì nó thay đổi quan hệ readability bên ngoài descriptor.

**--add-modules** cũng không thay thế **--add-exports** hoặc **--add-opens**. Các tùy chọn đó giải quyết quyền truy cập package hoặc reflection, còn **--add-modules** chỉ đưa module vào tập phân giải.

## 9. Kiểm tra module và kết quả biên dịch

Sau khi biên dịch, có thể kiểm tra module trong output:

~~~bash
java --module-path out:lib --list-modules
~~~

Kiểm tra descriptor của module đã biên dịch:

~~~bash
java --module-path out --describe-module com.example.app
~~~

Nếu module phụ thuộc là một JAR, có thể xem descriptor của nó:

~~~bash
jar --describe-module --file lib/com.example.codec.jar
~~~

Những lệnh này giúp xác nhận tên module mà JDK nhận diện. Nếu tên module khác với tên đang ghi trong **requires**, hãy kiểm tra descriptor hoặc automatic module name của JAR.

Khi build cho một phiên bản Java cụ thể, có thể dùng **--release**:

~~~bash
javac --release 17 \
      --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

**--release** kiểm soát phiên bản ngôn ngữ, bytecode và API nền tảng mà mã nguồn được phép sử dụng. Hãy chọn release phù hợp với runtime mục tiêu; không nên chỉ dựa vào phiên bản JDK đang cài trên máy biên dịch.

## 10. Các lỗi thường gặp và cách xử lý

**module not found**

Module được khai báo trong **requires** hoặc **--add-modules** không được tìm thấy. Kiểm tra module path, tên module, tên JAR và module descriptor. Nếu dùng thư mục exploded module, bảo đảm thư mục chứa **module-info.class** ở đúng cấp.

**package is not visible**

Module phụ thuộc đã được tìm thấy nhưng package cần dùng chưa được module đó xuất. Kiểm tra **exports** trong descriptor của module cung cấp. Thêm **--add-modules** không thể thay thế khai báo exports.

**module does not read ...**

Module hiện tại chưa có quan hệ readability đến module chứa API. Với named module, kiểm tra **requires** trong module descriptor. Với tình huống đặc biệt có thể cần **--add-reads**, nhưng chỉ nên dùng khi hiểu rõ quan hệ module mong muốn.

**package does not exist**

Có thể JAR đang đặt nhầm trên classpath hoặc module path, package không được export, hoặc dependency chưa có trong build. Kiểm tra cách thư viện được phân loại và tên module thực tế bằng **jar --describe-module**.

**Module name does not match**

Tên trong **requires** phải khớp tên module mà JDK nhận diện. Với automatic module, kiểm tra **Automatic-Module-Name** hoặc tên suy ra từ tên JAR. Không nên tự đổi tên file mà không xác nhận module name.

**Biên dịch được nhưng runtime báo thiếu module**

Classpath và module path khi chạy phải cung cấp đúng các thành phần tương ứng. Module cần được phân giải trong runtime graph; nếu phụ thuộc được chọn động, hãy bổ sung module vào cấu hình khởi chạy hoặc runtime image phù hợp.

## 11. Quy trình build modular đề xuất

Khi xây dựng ứng dụng JPMS, có thể thực hiện theo trình tự:

1. Tổ chức source tree theo tên module và đặt **module-info.java** trong từng module.
2. Xác định JAR thư viện nào là modular module, automatic module hoặc thư viện classpath.
3. Đặt module phụ thuộc vào **--module-path**.
4. Khai báo các phụ thuộc trực tiếp bằng **requires** trong module descriptor.
5. Dùng **--module-source-path** và **-m** để chọn module nguồn cần biên dịch.
6. Chỉ dùng **--add-modules** khi cần thêm module vào tập phân giải; không dùng nó để che thiếu khai báo requires.
7. Ghi output vào thư mục riêng bằng **-d**.
8. Kiểm tra tên module và descriptor sau khi biên dịch.
9. Chạy ứng dụng với module path tương ứng và kiểm thử các chức năng.
10. Ghi lại phiên bản JDK, release mục tiêu, module path và lệnh build để tái lập trong CI.

Ví dụ lệnh biên dịch tổng hợp:

~~~bash
javac \
  --release 17 \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.model,com.example.app
~~~

Nếu dự án có module bổ sung cần được phân giải ngoài các module gốc, thêm **--add-modules** với tên cụ thể và kiểm tra lại module graph.

## 12. Ghi nhớ

- **--module-path** hoặc **-p** cho javac biết nơi tìm named module và automatic module.
- **--module-source-path** tổ chức mã nguồn của nhiều module.
- **-m** hoặc **--module** chọn module cần biên dịch.
- **--add-modules** thêm module vào tập module gốc cần phân giải.
- **requires** trong **module-info.java** mới là khai báo phụ thuộc trực tiếp của named module.
- **exports**, **opens**, **--add-reads** và **--add-exports** giải quyết các khía cạnh truy cập khác nhau; chúng không đồng nghĩa với việc thêm module vào module graph.
- Dùng **--release** khi cần build cho phiên bản Java mục tiêu và xác minh module name của JAR trước khi kết luận module path đã đúng.

Khi hiểu rõ vai trò của module path, requires và add-modules, quá trình biên dịch ứng dụng modular trở nên có thể dự đoán và tái lập. Descriptor mô tả phụ thuộc thực sự của module; tùy chọn dòng lệnh điều khiển phạm vi biên dịch và phân giải cho từng lần build.
