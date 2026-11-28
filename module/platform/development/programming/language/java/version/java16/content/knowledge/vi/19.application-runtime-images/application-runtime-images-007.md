# Giới hạn của automatic module khi xây runtime bằng jlink

## 1. Automatic module là gì?

JPMS (Java Platform Module System) được giới thiệu từ Java 9. Để hỗ trợ quá trình chuyển đổi từ thư viện JAR truyền thống sang module, Java cho phép đặt một JAR chưa có module descriptor lên module path. Khi đó JAR được xem là một *automatic module*.

Một automatic module có các đặc điểm:

- JAR không có `module-info.class` hợp lệ.
- Nếu manifest có thuộc tính `Automatic-Module-Name`, giá trị đó được dùng làm tên module.
- Nếu không có thuộc tính trên, tên module được suy ra từ tên file JAR.
- Khi chạy trong module system, automatic module được xử lý đặc biệt: nó đọc các module quan sát được và các package của nó được xem như export/open.

Automatic module giúp một ứng dụng đã module hóa có thể phụ thuộc vào thư viện cũ trong giai đoạn chuyển đổi. Đây vẫn là cơ chế tương thích của JPMS. Tuy nhiên, nó có giới hạn quan trọng khi tạo runtime image bằng `jlink`.

## 2. Phân biệt classpath, automatic module và explicit module

Cùng một JAR không có module descriptor sẽ được xử lý khác nhau tùy vị trí triển khai:

| Cách đặt JAR | Cách Java xem JAR | Có thể làm module root cho `jlink`? |
| --- | --- | --- |
| Trên classpath | Thuộc unnamed module | Không |
| Trên module path, không có `module-info.class` | Automatic module | Không |
| Trên module path, có module descriptor hợp lệ | Explicit named module | Có |

Ví dụ:

~~~powershell
# Xem cách Java nhận diện một JAR
jar --describe-module --file lib\legacy-json.jar
~~~

Nếu JAR không có module descriptor, đầu ra thường cho biết không tìm thấy module descriptor và tên automatic module được suy ra. Nếu JAR có explicit module descriptor, lệnh hiển thị tên module cùng các khai báo như `requires`, `exports`, `opens`, `uses` hoặc `provides`.

Một JAR có `Automatic-Module-Name` vẫn là automatic module nếu không có `module-info.class`. Thuộc tính này chỉ giúp giữ tên module ổn định khi JAR được đặt trên module path; nó không biến JAR thành explicit module.

## 3. Vì sao jlink không liên kết automatic module?

`jlink` tạo runtime image từ các module có thể liên kết, gồm:

- Module JDK được cung cấp dưới dạng JMOD.
- Modular JAR có module descriptor rõ ràng.
- Exploded module có cấu trúc module hợp lệ.

Automatic module không có module descriptor tường minh để mô tả đầy đủ dependency, package export và service contract theo cách `jlink` cần khi liên kết image. Vì vậy, automatic module không được hỗ trợ làm đầu vào của module graph dùng để tạo runtime image.

Khi module path của `jlink` chứa automatic module thuộc graph cần liên kết, lệnh có thể dừng với lỗi dạng:

~~~text
Error: automatic module cannot be used with jlink: legacy.json
~~~

Ví dụ, ứng dụng có module descriptor:

~~~java
module com.example.app {
    requires legacy.json;
}
~~~

Nếu `legacy-json.jar` chỉ là JAR thường và được nhận diện thành automatic module `legacy.json`, ứng dụng có thể chạy trên một JDK đầy đủ với module path phù hợp. Nhưng khi dùng `jlink` để liên kết module ứng dụng cùng dependency đó, quá trình liên kết thất bại.

Đây là giới hạn của bước tạo runtime image, không phải bằng chứng rằng automatic module không thể chạy trong Java module system.

## 4. Automatic-Module-Name không khắc phục giới hạn này

Một thư viện có thể khai báo tên module ổn định trong manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacyjson
~~~

Sau đó module ứng dụng có thể viết:

~~~java
module com.example.app {
    requires com.example.legacyjson;
}
~~~

Điều này hữu ích để tránh tên module bị thay đổi theo tên file JAR. Nhưng nếu JAR vẫn không có module descriptor, Java vẫn xem nó là automatic module. `jlink` vẫn không thể liên kết module đó.

Không nên xử lý lỗi bằng cách chỉ thêm hoặc đổi `Automatic-Module-Name`. Muốn dùng dependency làm đầu vào cho `jlink`, cần một explicit module có module descriptor thực sự.

## 5. Cách nhận diện dependency đang chặn jlink

Khi `jlink` báo automatic module, hãy xác định JAR nào tạo ra module đó và kiểm tra toàn bộ dependency bắc cầu.

**Bước 1 — xem descriptor của từng JAR trên module path:**

~~~powershell
jar --describe-module --file lib\legacy-json.jar
jar --describe-module --file lib\legacy-http.jar
~~~

**Bước 2 — phân tích dependency tĩnh:**

~~~powershell
jdeps --list-deps --module-path "mods;lib" --module com.example.app
~~~

`jdeps` giúp xem các module được tham chiếu qua bytecode và module path. Kết quả cần được đối chiếu với cấu hình reflection, plugin và service vì những dependency được chọn bằng tên chuỗi có thể không xuất hiện trong phân tích tĩnh.

**Bước 3 — kiểm tra cả dependency bắc cầu.** Một thư viện explicit module có thể `requires` một automatic module khác. Dù module chính có descriptor hợp lệ, `jlink` vẫn không thể liên kết nếu module graph cần chứa automatic module.

Hãy lập danh sách theo từng dependency:

| Thư viện | Loại module | Hành động |
| --- | --- | --- |
| Thư viện có `module-info.class` | Explicit module | Kiểm tra dependency và tiếp tục dùng với `jlink` |
| JAR không có descriptor, có `Automatic-Module-Name` | Automatic module | Nâng cấp, modular hóa hoặc giữ trên classpath |
| JAR không có descriptor và không có tên ổn định | Automatic module, tên suy ra từ file | Xác định đúng phiên bản, sau đó nâng cấp hoặc modular hóa |
| JAR được đặt trên classpath | Unnamed module | Đóng gói như dependency classpath; không thêm vào module roots |

## 6. Giải pháp ưu tiên: dùng phiên bản thư viện có explicit module

Nếu nhà cung cấp thư viện đã phát hành phiên bản modular, hãy nâng cấp dependency lên phiên bản có `module-info.class`. Một số thư viện cung cấp module descriptor trực tiếp trong JAR; một số thư viện dùng multi-release JAR với module descriptor trong thư mục phiên bản phù hợp.

Sau khi nâng cấp:

1. Kiểm tra descriptor bằng `jar --describe-module`.
2. Xem các dependency mới bằng `jdeps`.
3. Cập nhật `requires` trong module ứng dụng nếu tên module thay đổi.
4. Kiểm tra các package API, service và quyền reflection.
5. Chạy lại `jlink` và test runtime image.

Một multi-release JAR có thể chứa `module-info.class` trong `META-INF/versions/9` hoặc thư mục phiên bản phù hợp. Vì vậy, không nên chỉ tìm file ở thư mục gốc bằng công cụ ZIP rồi kết luận JAR không modular; hãy dùng `jar --describe-module` để xem cách JDK nhận diện.

## 7. Nếu sở hữu mã nguồn thư viện, tạo explicit module descriptor

Nếu bạn kiểm soát thư viện, có thể bổ sung `module-info.java` và build lại thành modular JAR:

~~~java
module com.example.legacyjson {
    requires java.logging;

    exports com.example.legacyjson.api;
}
~~~

Descriptor phải phản ánh đúng thiết kế:

- `requires` khai báo module mà thư viện cần đọc.
- `exports` chỉ mở các package API cần cho module khác biên dịch và gọi.
- `opens` chỉ dùng khi framework cần deep reflection vào package.
- `uses` và `provides` mô tả service contract và provider nếu thư viện sử dụng SPI.

Sau khi build lại JAR, xác nhận module descriptor đã được đóng gói:

~~~powershell
jar --describe-module --file build\legacy-json-modular.jar
~~~

Đầu ra phải cho thấy descriptor của explicit module, thay vì thông báo không có descriptor và suy ra automatic module.

Không nên tạo descriptor chỉ để làm cho `jlink` hết báo lỗi. Nếu khai báo thiếu `requires`, `exports` hoặc service, ứng dụng có thể biên dịch được nhưng lỗi khi chạy. Nếu xuất package quá rộng hoặc mở toàn module, ranh giới đóng gói bị suy yếu. Hãy thiết kế descriptor dựa trên API và dependency thực tế.

## 8. Dùng jdeps --generate-module-info làm điểm khởi đầu

Với thư viện cũ có nhiều package, `jdeps` có thể tạo một bản nháp module descriptor:

~~~powershell
jdeps --generate-module-info generated lib\legacy-json.jar
~~~

Công cụ phân tích JAR và sinh file `module-info.java` trong thư mục đầu ra. Đây chỉ là bản nháp để hỗ trợ chuyển đổi:

- Kiểm tra lại các dependency được đề xuất.
- Xác nhận package nào thực sự cần `exports`.
- Bổ sung hoặc điều chỉnh `opens` cho framework dùng reflection khi cần.
- Kiểm tra service interface và provider.
- Xử lý dependency khác vẫn là automatic module.
- Biên dịch descriptor vào JAR và kiểm tra lại bằng `jar --describe-module`.

`jdeps --generate-module-info` không tự sửa JAR thành explicit module và không tự giải quyết toàn bộ vấn đề tương thích. Nó cũng không thay thế kiểm thử tích hợp sau khi modular hóa.

## 9. Nếu không thể modular hóa dependency, chuyển ứng dụng sang classpath packaging

Một lựa chọn thực tế là triển khai ứng dụng dưới dạng classpath application nếu kiến trúc ứng dụng cho phép. Khi JAR nằm trên classpath, nó thuộc unnamed module; nó không trở thành automatic module trên module path. `jlink` có thể tạo runtime chỉ từ các module JDK cần thiết, còn `jpackage` đóng gói JAR ứng dụng và các thư viện classpath.

Ví dụ thư mục đầu vào:

~~~text
input/
  app.jar
  legacy-json.jar
  legacy-http.jar
~~~

Tạo runtime chứa các module JDK cần thiết:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging,java.net.http --output build\runtime
~~~

Đóng gói ứng dụng classpath cùng runtime:

~~~powershell
jpackage --type app-image --name LegacyApp --input input --main-jar app.jar --main-class com.example.app.Main --runtime-image build\runtime --dest dist
~~~

Trong cách này:

- Các JAR trong thư mục `input` được đưa vào application image.
- `jpackage` tạo launcher cho `app.jar` và mặc định xây classpath từ các JAR trong thư mục input.
- `legacy-json.jar` và `legacy-http.jar` chạy trên classpath, không phải automatic module.
- Runtime image chỉ chứa các module JDK được chọn bằng `jlink`.

Danh sách module JDK trong ví dụ chỉ minh họa. Hãy dùng `jdeps` để phân tích dependency nền tảng thực tế và kiểm thử các chức năng nạp động.

Nếu JAR ứng dụng có `module-info.class` nhưng được khởi chạy bằng `--main-jar`, descriptor đó không được dùng để tạo named module; các lớp chạy trong unnamed module trên classpath.

Lưu ý quan trọng: không thể chỉ chuyển một dependency từ module path sang classpath mà giữ nguyên ứng dụng ở dạng explicit module nếu module đó vẫn khai báo `requires` dependency ấy. Named module không đọc unnamed module theo cách thông thường. Chuyển sang classpath packaging có thể yêu cầu thay đổi cách khởi chạy và cấu trúc module của chính ứng dụng.

## 10. Nếu cần giữ ứng dụng modular và automatic module

Automatic module vẫn có thể được resolve khi chạy trên một JDK đầy đủ. Ví dụ, ứng dụng module hóa `com.example.app` có thể được chạy với JAR automatic module trên module path:

~~~powershell
java --module-path "mods;lib\legacy-json.jar" --module com.example.app/com.example.app.Main
~~~

Điều này phù hợp khi cần duy trì module graph hiện tại và chấp nhận phân phối một Java runtime tiêu chuẩn có module system đầy đủ (chẳng hạn runtime đi cùng bản JDK) theo chính sách triển khai. Java launcher có thể resolve automatic module; giới hạn xuất hiện khi cố liên kết module đó vào runtime image bằng `jlink`.

Nếu mục tiêu bắt buộc là runtime image tối giản do `jlink` tạo, dependency trong module graph cần được chuyển thành explicit module hoặc thay thế bằng phiên bản modular. Chỉ truyền một runtime image dựng sẵn cho `jpackage` không biến automatic module thành explicit module.

## 11. Những cách xử lý không giải quyết được vấn đề

- **Chỉ thêm `Automatic-Module-Name`:** tên module ổn định hơn nhưng JAR vẫn là automatic module.
- **Chỉ thêm tên vào `--add-modules`:** tùy chọn này chọn module roots; nó không tạo module descriptor hoặc biến automatic module thành explicit module.
- **Đổi thứ tự module path:** không thay đổi loại module.
- **Dùng `--bind-services`:** tùy chọn này liên kết service provider module; nó không chuyển automatic module thành explicit module.
- **Dùng `--ignore-missing-deps`:** không giải quyết giới hạn automatic module và có thể che khuất dependency chưa được phân tích.
- **Đưa JAR vào classpath nhưng vẫn giữ `requires`:** module descriptor của ứng dụng vẫn yêu cầu named module, trong khi JAR trên classpath thuộc unnamed module.

Hãy chọn một trong các hướng có thể kiểm soát: nâng cấp dependency, tạo explicit module descriptor, chuyển toàn bộ ứng dụng sang classpath nếu phù hợp, hoặc giữ runtime đầy đủ và không dùng `jlink` cho module graph có automatic module.

## 12. Quy trình quyết định

| Tình huống | Hướng xử lý |
| --- | --- |
| Dependency đã có explicit module | Dùng module path và tiếp tục tạo runtime bằng `jlink` |
| Dependency có phiên bản mới đã modular | Nâng cấp và kiểm tra tương thích |
| Bạn kiểm soát mã nguồn thư viện | Bổ sung descriptor, build lại và test |
| Thư viện cũ không thể modular hóa, ứng dụng có thể chạy classpath | Đóng gói classpath application với runtime JDK tùy chỉnh |
| Ứng dụng phải giữ module graph có automatic module | Chạy với runtime đầy đủ, không liên kết graph đó bằng `jlink` |

**Ghi nhớ:** Automatic module là cầu nối tương thích khi đưa JAR cũ lên module path, nhưng `jlink` chỉ liên kết explicit modules, JMOD và exploded modules. `Automatic-Module-Name` không biến JAR thành explicit module. Hãy ưu tiên dependency đã modular, hoặc tạo descriptor có kiểm thử; nếu không thể, cân nhắc classpath packaging hay runtime đầy đủ phù hợp với cách ứng dụng được triển khai.

## Nguồn tham khảo chính thức

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [ModuleFinder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
