# Runtime error do module không resolve

## 1. Module resolution diễn ra trước khi chạy ứng dụng

Với ứng dụng dùng Java Platform Module System (JPMS), JVM cần xây dựng **module graph** trước khi nạp main class và thực thi chương trình. Graph bắt đầu từ các root module, sau đó resolver tìm các module mà chúng yêu cầu trực tiếp hoặc gián tiếp qua directive **requires**.

Một lệnh chạy modular thường có dạng:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Trong đó:

- **--module-path mods** chỉ định nơi Java tìm các named module và automatic module.
- **-m com.acme.app/com.acme.app.Main** yêu cầu chạy main class thuộc module **com.acme.app**.
- Module descriptor và dependency của root module được kiểm tra trước khi main class bắt đầu chạy.

Nếu một module bắt buộc không được tìm thấy, module graph có xung đột hoặc module không thể được resolve, chương trình dừng trước khi vào main. Đây là nhóm lỗi cần xử lý ở cấu hình module path và module descriptor.

## 2. Ví dụ ứng dụng modular tối thiểu

Giả sử ứng dụng có hai module:

~~~text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Message.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Module API:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Class API:

~~~java
package com.acme.api;

public record Message(String value) {
}
~~~

Module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.api.Message;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("JPMS is running");
        System.out.println(message.value());
    }
}
~~~

Biên dịch các module từ source tree:

~~~bash
javac --module-source-path src \
  -d mods \
  -m com.acme.api,com.acme.app
~~~

Chạy module ứng dụng:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
JPMS is running
~~~

Nếu lệnh chạy không tìm được com.acme.api, hãy kiểm tra module path và tên module trước khi thay đổi source code.

## 3. Phân loại lỗi theo thông báo

Các lỗi sau thường gặp khi module graph không thể được tạo hoặc khi runtime chuyển sang giai đoạn nạp class:

| Dấu hiệu | Ý nghĩa thường gặp | Nơi cần kiểm tra |
|---|---|---|
| java.lang.module.FindException: Module X not found | Resolver không tìm thấy module X được yêu cầu | Module path, tên module, vị trí JAR/thư mục module |
| FindException: Error reading module hoặc lỗi đọc descriptor | Artifact hỏng, descriptor không hợp lệ hoặc không thể đọc | JAR, module-info.class, định dạng artifact |
| ResolutionException | Module graph không nhất quán hoặc không thể giải quyết | Dependency, package overlap, phiên bản và ranh giới module |
| LayerInstantiationException | Không thể tạo layer từ configuration đã resolve | Module graph, package/class loader constraints và cách tạo layer |
| Could not find or load main class | Module có thể đã được tìm thấy nhưng main class không đúng hoặc không có trong artifact | Tên main class, package, nội dung JAR và lệnh -m |
| ClassNotFoundException hoặc NoClassDefFoundError | Lỗi nạp class sau hoặc trong quá trình chạy | Class có trong artifact không, dependency/class loader |
| IllegalAccessError | Runtime không cho phép truy cập type/member theo module boundary | exports, readability và artifact runtime có khớp lúc compile không |
| InaccessibleObjectException | Reflection truy cập sâu bị module encapsulation chặn | opens và cách framework truy cập |

Không nên gom mọi lỗi runtime thành “module không resolve”. Ví dụ, FindException xảy ra khi tìm hoặc resolve module, còn ClassNotFoundException có thể xảy ra sau khi module graph đã được tạo thành công.

## 4. Lỗi phổ biến: thiếu module trên module path

Giả sử com.acme.app khai báo:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Nhưng khi chạy, lệnh chỉ đưa ứng dụng lên module path:

~~~bash
java --module-path app.jar \
  -m com.acme.app/com.acme.app.Main
~~~

Nếu com.acme.api nằm trong api.jar mà không được đưa vào module path, resolver có thể báo:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.acme.api not found,
required by com.acme.app
~~~

Cách sửa là cung cấp cả hai artifact:

~~~bash
java --module-path "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

Trên Windows, dấu phân cách giữa các phần tử của module path là dấu chấm phẩy:

~~~powershell
java --module-path "app.jar;api.jar" -m com.acme.app/com.acme.app.Main
~~~

Nếu các module đã được đặt trong cùng thư mục mods, có thể dùng:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Đảm bảo mods thực sự chứa các modular JAR hoặc exploded module directories. Chỉ đặt JAR trên ổ đĩa không khiến JVM tự động tìm thấy nó.

## 5. Đặt dependency nhầm trên classpath

Một lỗi chuyển đổi thường gặp là dependency có trên classpath nhưng module ứng dụng lại khai báo requires tới nó.

Ví dụ:

~~~bash
java -cp "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

Classpath phục vụ classpath/unnamed module. Nó không thay thế module path để thỏa mãn một dependency requires com.acme.api của named module.

Với ứng dụng modular, hãy đặt dependency trên module path:

~~~bash
java --module-path "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

Nếu dependency là JAR không có module-info.class, khi đặt trên module path nó có thể được xem là **automatic module**. Tên module thường được suy ra từ tên JAR, trừ khi JAR khai báo Automatic-Module-Name. Hãy kiểm tra tên thực tế thay vì đoán từ tên file.

## 6. Tên module không khớp với tên file hoặc tên package

Tên module được khai báo trong descriptor:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Consumer phải dùng đúng tên đó:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Tên module không phải tên package và cũng không nhất thiết giống nguyên văn tên JAR. Với explicit module, descriptor là nguồn xác định tên module. Với automatic module, có thể kiểm tra tên suy ra hoặc tên được khai báo trong manifest.

Dùng lệnh sau để xem descriptor của JAR:

~~~bash
jar --describe-module --file mods/acme-api.jar
~~~

Nếu module name hiển thị khác với tên trong requires, sửa dependency hoặc cấu hình đóng gói để thống nhất.

## 7. Kiểm tra module path và các module có thể quan sát

Một số lệnh hữu ích:

Liệt kê các module mà runtime nhận diện:

~~~bash
java --list-modules --module-path mods
~~~

Xem descriptor của một JAR:

~~~bash
jar --describe-module --file mods/acme-api.jar
~~~

Validate các module trên module path:

~~~bash
java --validate-modules \
  --module-path mods \
  --add-modules ALL-MODULE-PATH
~~~

Kiểm tra dependency của module:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

Các lệnh này phục vụ các mục đích khác nhau: liệt kê module, xem descriptor, kiểm tra module graph và phân tích dependency. Một lệnh thành công không đảm bảo mọi class sẽ nạp được khi chạy, vì vậy vẫn cần integration test trên module path.

## 8. Bật thông tin chi tiết về quá trình resolution

Khi ứng dụng chạy bằng Java launcher, thêm **--show-module-resolution** để xem các module được resolve:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Thông tin hiển thị giúp xác định:

- Root module nào được yêu cầu.
- Module nào được tìm thấy và resolve.
- Dependency nào được đưa vào graph.
- Service binding nào có thể đưa provider module vào graph.

Nếu lệnh dừng trước khi in output của ứng dụng, đọc phần thông báo ngay sau thông tin resolution để tìm module thiếu hoặc conflict.

Có thể tăng mức chẩn đoán class loading bằng:

~~~bash
java -Xlog:class+load=info \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Log class loading giúp điều tra lỗi xảy ra sau khi module graph đã được tạo, chẳng hạn class bị thiếu hoặc được nạp từ nguồn không mong muốn. Nó không thay thế --show-module-resolution.

## 9. Các option có thể làm thay đổi module graph

Khi đọc lệnh chạy, cần chú ý các option sau:

- **--module-path**: chỉ định các module có thể được tìm thấy.
- **--add-modules**: thêm module root ngoài root mặc định. Có thể chỉ định tên module hoặc ALL-MODULE-PATH.
- **--limit-modules**: giới hạn tập module có thể quan sát; một dependency vốn có thể tìm thấy có thể trở nên không khả dụng.
- **--upgrade-module-path**: cung cấp module thay thế cho một số module hệ thống theo quy tắc upgrade module path.
- **--add-reads**: bổ sung quan hệ readability ở runtime.
- **--add-exports**: mở quyền truy cập public API của package cho module đích.
- **--add-opens**: cho phép reflective access sâu vào package ở runtime.

--add-reads, --add-exports và --add-opens thay đổi ranh giới truy cập; chúng không làm một JAR bị thiếu tự xuất hiện trên module path. Nếu thông báo là Module X not found, hãy sửa module discovery trước.

--add-modules cũng không thể tìm module nằm ngoài các nguồn mà module finder/runtime quan sát được. Nó yêu cầu resolver đưa một module đã có thể tìm thấy vào graph.

## 10. Runtime error không phải lúc nào cũng là resolution error

Sau khi module graph resolve thành công, ứng dụng vẫn có thể lỗi ở các giai đoạn tiếp theo:

- Main class không tồn tại hoặc tên class trong lệnh -m sai.
- Một class dependency không có trong JAR hoặc class loader không tìm thấy.
- Artifact runtime cũ hơn hoặc khác với artifact dùng khi compile.
- Public package không được export hoặc module không đọc dependency như dự kiến.
- Framework dùng reflection sâu nhưng package chưa được mở bằng opens.
- Bytecode được biên dịch bằng JDK mới hơn runtime đang chạy, dẫn tới UnsupportedClassVersionError.

Vì vậy, khi thấy lỗi, hãy xác định nó xảy ra trước hay sau khi module graph được tạo. Không nên thêm --add-opens hoặc thay đổi requires nếu lỗi thực tế là sai tên main class hoặc thiếu class trong JAR.

## 11. Quy trình chẩn đoán thực tế

Khi nhận lỗi runtime liên quan module, thực hiện lần lượt:

1. **Đọc exception đầu tiên.** Phân biệt FindException, ResolutionException, lỗi tạo layer và lỗi nạp class.
2. **Xác nhận module chính.** Kiểm tra tên module trong lệnh -m và module descriptor của artifact.
3. **Kiểm tra module path.** Xác nhận thư mục/JAR chứa root module và mọi dependency requires đều được cung cấp.
4. **Xác nhận module name.** Dùng jar --describe-module để xem tên thực tế.
5. **In module resolution.** Chạy lại với --show-module-resolution để xem graph.
6. **Validate graph.** Dùng java --validate-modules và jdeps --check khi cần.
7. **Kiểm tra class loading.** Nếu resolution thành công, chuyển sang kiểm tra nội dung JAR, classpath/module path, class loader, exports/opens và phiên bản JDK.
8. **Chạy integration test trên module path.** Đừng chỉ kiểm thử bằng classpath nếu artifact cuối cùng được phát hành như named modules.

## 12. Ví dụ checklist phát hành

Một pipeline có thể chạy các lệnh sau trên thư mục staging cuối cùng:

~~~bash
jar --describe-module --file dist/acme-app.jar

java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH

java --show-module-resolution \
  --module-path dist \
  -m com.acme.app/com.acme.app.Main
~~~

Trong CI, cấu hình các bước này là required checks. Nếu module không tìm thấy hoặc graph không hợp lệ, pipeline nên dừng trước khi publish artifact.

Đối với môi trường chạy thực tế, cần kiểm tra chính xác tập JAR được deploy, option JVM thực tế, biến môi trường và script khởi động. Một lệnh chạy local có module path khác production có thể che giấu lỗi đóng gói.

## Ghi nhớ

- Module graph được resolve trước khi main class chạy.
- FindException: Module X not found thường chỉ ra module path, tên module hoặc nguồn tìm kiếm.
- Dependency requires của named module phải có thể được tìm thấy trên module path hoặc trong parent configuration phù hợp.
- --show-module-resolution, --list-modules, jar --describe-module, java --validate-modules và jdeps --check hỗ trợ chẩn đoán ở các góc độ khác nhau.
- --add-modules chọn thêm root module đã quan sát được; nó không sửa module path sai.
- Phân biệt lỗi resolution với lỗi main class, class loading, access, reflection và tương thích bytecode.
