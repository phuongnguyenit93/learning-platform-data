# Phân tích dependency bằng jdeps trong Java

jdeps là công cụ phân tích dependency tĩnh đi kèm JDK. Công cụ đọc class file, JAR hoặc thư mục class để cho biết một ứng dụng phụ thuộc vào package, class và module nào. jdeps hữu ích khi kiểm tra thư viện trước khi nâng JDK, tìm tham chiếu tới JDK internal API, chuẩn bị chuyển ứng dụng sang Java Platform Module System (JPMS), xác định module cần cho jlink và điều tra dependency bị thiếu.

jdeps phân tích những tham chiếu có thể quan sát từ bytecode và metadata. Nó không thực thi chương trình, không chứng minh mọi nhánh runtime đều hoạt động và không phát hiện chắc chắn mọi dependency được nạp qua reflection, tên class trong cấu hình, JNI hoặc code sinh lúc chạy. Vì vậy, hãy kết hợp báo cáo jdeps với build, test và smoke test trên runtime mục tiêu.

Bài này đi từ một JAR mẫu đến các lệnh phân tích class/package/module, dependency bị thiếu, JDK internal API, sơ đồ DOT và module descriptor. Các ví dụ được kiểm tra với jdeps 24.0.2; output có thể khác đôi chút giữa các phiên bản JDK.

## 1. jdeps dùng để làm gì?

jdeps trả lời các câu hỏi về dependency tĩnh:

- Một JAR đang tham chiếu tới package và class nào?
- Module JDK nào được ứng dụng sử dụng?
- Có dependency nào không tìm thấy trên classpath/module path không?
- Source hoặc dependency có tham chiếu tới JDK internal API không?
- Package nào phụ thuộc vào package khác?
- Khi chuyển sang JPMS, module descriptor cần khai báo những requires nào?
- Module nào cần thiết để tạo runtime image tối giản bằng jlink?
- Module nào đang phụ thuộc vào một package hoặc module cụ thể?

Ví dụ, một ứng dụng có thể import java.sql, java.net.http và java.time. jdeps có thể tổng hợp các tham chiếu này thành dependency tới java.sql, java.net.http và java.base.

jdeps là công cụ phân tích, không phải compiler, dependency resolver hay test runner. Nó không thay thế javac, Maven/Gradle dependency analysis, unit test hoặc integration test.

## 2. jdeps nằm ở đâu và kiểm tra version thế nào?

jdeps được phân phối cùng JDK, nằm trong thư mục bin:

Windows:

~~~powershell
where.exe jdeps
jdeps --version
~~~

Linux/macOS:

~~~bash
command -v jdeps
jdeps --version
~~~

Nếu lệnh không được tìm thấy, kiểm tra JAVA_HOME và PATH. Có thể gọi trực tiếp:

Windows:

~~~powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --version
~~~

Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeps" --version
~~~

Nên dùng jdeps từ JDK phù hợp với class-file version và module metadata cần phân tích. Một bản jdeps quá cũ có thể không đọc được class file được tạo bởi JDK mới hơn. Ghi lại version của java, javac và jdeps trong CI để kết quả có thể giải thích và tái hiện.

Xem option được hỗ trợ bởi chính phiên bản đang chạy:

~~~powershell
jdeps --help
~~~

Tên option và khả năng phân tích có thể được bổ sung giữa các JDK. Khi viết script dùng lâu dài, kiểm tra help của JDK đã pin thay vì giả định mọi máy có cùng bộ option.

## 3. Đầu vào mà jdeps có thể phân tích

jdeps nhận một hoặc nhiều đầu vào:

- File .class đơn lẻ.
- Thư mục chứa package/class đã biên dịch.
- JAR thường.
- JAR có module descriptor.
- Multi-release JAR.
- Module hoặc tập module khi dùng module analysis options.

Ví dụ:

~~~powershell
jdeps out\demo\App.class
jdeps out
jdeps app.jar
~~~

Với thư mục class, jdeps quét các class trong thư mục đó. Với JAR, công cụ đọc class và metadata trong archive. Có thể truyền nhiều JAR cùng một lệnh để xem quan hệ giữa các artifact.

Nên phân tích artifact sau khi build, vì đó là nội dung thực tế sẽ được đóng gói và phát hành. Phân tích thư mục target/classes hoặc build/classes cũng hữu ích trong quá trình phát triển, nhưng không thay thế việc kiểm tra JAR cuối cùng.

## 4. Tạo dự án mẫu để thực hành

Ví dụ dùng một thư viện nhỏ tên dependency.jar và ứng dụng app.jar. Ứng dụng tham chiếu tới class từ thư viện, đồng thời sử dụng một số module JDK.

Cấu trúc source:

~~~text
jdeps-demo/
  src/
    dep/
      api/
        Marker.java
    app/
      demo/
        App.java
~~~

File src/dep/api/Marker.java:

~~~java
package dep.api;

public final class Marker {
    public String name() {
        return "marker";
    }
}
~~~

File src/app/demo/App.java:

~~~java
package demo;

import dep.api.Marker;
import java.net.http.HttpClient;
import java.sql.Connection;
import java.time.Instant;

public final class App {
    public static void main(String[] args) {
        Marker marker = new Marker();
        Class<?>[] types = { Connection.class, HttpClient.class };

        System.out.println(marker.name());
        System.out.println("JDK types: " + types.length);
        System.out.println(Instant.EPOCH);
    }
}
~~~

Compile và đóng gói trên Windows PowerShell, Linux hoặc macOS từ thư mục jdeps-demo:

~~~powershell
javac -d dep-classes src\dep\api\Marker.java
jar --create --file dependency.jar -C dep-classes .

javac -cp dependency.jar -d app-classes src\app\demo\App.java
jar --create --file app.jar -C app-classes .
~~~

Trên Linux/macOS, thay dấu gạch chéo ngược trong source path bằng dấu /:

~~~bash
javac -d dep-classes src/dep/api/Marker.java
jar --create --file dependency.jar -C dep-classes .

javac -cp dependency.jar -d app-classes src/app/demo/App.java
jar --create --file app.jar -C app-classes .
~~~

Kết quả là hai artifact:

- dependency.jar chứa dep.api.Marker.
- app.jar chứa demo.App, tham chiếu dep.api.Marker, java.sql, java.net.http và java.time.

Ứng dụng được compile với dependency.jar trên classpath. Khi phân tích app.jar, phải cung cấp lại dependency đó để jdeps resolve được tham chiếu ngoài JDK.

## 5. Phân tích dependency cơ bản

Chạy:

~~~powershell
jdeps app.jar
~~~

Lệnh mặc định hiển thị quan hệ dependency ở mức package. Output có thể có dạng:

~~~text
app.jar -> dependency.jar
app.jar -> java.base
app.jar -> java.net.http
app.jar -> java.sql
demo -> dep.api
demo -> java.net.http
demo -> java.sql
~~~

Kết quả chính xác phụ thuộc classpath, JDK và các package được tham chiếu. Nếu không truyền dependency.jar vào classpath, jdeps có thể báo một package không tìm thấy thay vì hiện mối quan hệ tới JAR đó.

Chỉ định classpath:

~~~powershell
jdeps --class-path dependency.jar app.jar
~~~

--class-path cũng có alias -cp và -classpath. Dùng nó khi phân tích JAR không modular hoặc khi cần cung cấp các thư viện mà class file tham chiếu.

## 6. Phân biệt classpath và module path

Classpath chứa class và JAR truyền thống. Module path chứa các module có thể được nhận diện qua module descriptor hoặc cơ chế automatic module.

| Tùy chọn | Dùng khi |
|---|---|
| --class-path | Phân tích class/JAR trên classpath |
| --module-path | Phân tích named module và module graph |
| --module | Chỉ định module gốc cần phân tích |
| --upgrade-module-path | Cung cấp module thay thế cho module hệ thống trong module resolution |
| --system | Chỉ định system module image khác để phân tích |

Classpath có thể chứa nhiều entry. Trên Windows, separator thường là dấu chấm phẩy ;; trên Linux/macOS là dấu hai chấm :.

Ví dụ Windows:

~~~powershell
jdeps --class-path "lib\alpha.jar;lib\beta.jar" app.jar
~~~

Ví dụ Linux/macOS:

~~~bash
jdeps --class-path "lib/alpha.jar:lib/beta.jar" app.jar
~~~

Có thể dùng wildcard JAR theo quy tắc classpath của Java, ví dụ lib/*; hãy quote toàn bộ giá trị để shell không tự xử lý ký tự wildcard ngoài ý muốn.

Không đưa một JAR lên module path chỉ vì nó có đuôi .jar. Trước tiên xác định JAR có module-info.class, là automatic module hay chỉ là classpath library. Việc đặt sai đường dẫn có thể làm kết quả phân tích khác với cách ứng dụng thực sự được khởi chạy.

## 7. Xem dependency ở mức package hoặc class

Các mức chi tiết phổ biến:

~~~powershell
jdeps -summary app.jar
jdeps -verbose:package --class-path dependency.jar app.jar
jdeps -verbose:class --class-path dependency.jar app.jar
jdeps -v --class-path dependency.jar app.jar
~~~

Ý nghĩa:

- -summary hoặc -s: chỉ hiển thị tổng hợp dependency.
- -verbose:package: hiển thị dependency ở mức package.
- -verbose:class: hiển thị dependency ở mức class.
- -v: dạng verbose, tương đương class-level và bỏ lọc dependency mặc định.

Dùng summary khi cần báo cáo nhanh cho một JAR. Dùng package-level để hiểu kiến trúc giữa các package. Dùng class-level để tìm chính xác class nào tạo ra dependency không mong muốn.

Mặc định jdeps lọc một số dependency trong cùng package hoặc archive để output ngắn hơn. Có thể dùng -filter:none để hiển thị cả những quan hệ thường bị lọc:

~~~powershell
jdeps -verbose:class -filter:none app.jar
~~~

## 8. Phân tích dependency bắc cầu và lọc kết quả

-R hoặc --recursive yêu cầu jdeps đi theo dependency runtime bắc cầu. --no-recursive chỉ phân tích dependency trực tiếp.

~~~powershell
jdeps --recursive --class-path "lib/*" app.jar
~~~

Lọc package:

~~~powershell
jdeps --package java.sql app.jar
~~~

Lọc theo regular expression:

~~~powershell
jdeps --regex "java\..*" app.jar
~~~

Lọc theo module:

~~~powershell
jdeps --require java.sql app.jar
~~~

Lọc class được phân tích bằng --include:

~~~powershell
jdeps --include "demo\..*" -verbose:class app.jar
~~~

--package, --regex và --require là các bộ lọc dependency, không phải bộ lọc file đầu vào. --include giới hạn class được phân tích. Đọc help của version jdeps đang dùng để xác nhận các tổ hợp option hợp lệ; một số chế độ như --jdk-internals và --missing-deps có giới hạn riêng đối với filter.

## 9. Xem dependency module JDK

Để xem module JDK mà ứng dụng cần, dùng:

~~~powershell
jdeps --list-deps --class-path dependency.jar app.jar
~~~

Với JAR mẫu đã tạo, output thực tế trên JDK 24.0.2:

~~~text
java.base
java.net.http
java.sql
~~~

--list-deps liệt kê module dependency và có thể phân tích bắc cầu qua thư viện trên classpath/module path nếu chúng được tham chiếu. Dùng --no-recursive khi chỉ muốn xem dependency không bắc cầu.

Để lấy danh sách module dạng comma-separated:

~~~powershell
jdeps --print-module-deps --class-path dependency.jar app.jar
~~~

Output thực tế:

~~~text
java.base,java.net.http,java.sql
~~~

--print-module-deps in reduced module dependency list. Danh sách này có thể dùng làm đầu vào cho jlink --add-modules khi tạo custom runtime image, nhưng cần xác minh thêm service binding, reflection, native library và runtime configuration của ứng dụng trước khi phát hành image tối giản.

Các option liên quan:

- --list-deps: liệt kê module dependency.
- --list-reduced-deps: bỏ các cạnh đọc được suy ra từ quan hệ requires transitive.
- --print-module-deps: in danh sách module rút gọn, phân tách bằng dấu phẩy.
- --add-modules: thêm module gốc vào tập phân tích.

## 10. Phát hiện dependency bị thiếu bằng --missing-deps

Khi một class tham chiếu tới type không có trên classpath/module path, jdeps có thể báo dependency bị thiếu.

Với ví dụ trên, chạy mà không cung cấp dependency.jar:

~~~powershell
jdeps --missing-deps app.jar
~~~

Output thực tế:

~~~text
app.jar -> not found
   demo.App -> dep.api.Marker not found
~~~

Cung cấp dependency:

~~~powershell
jdeps --missing-deps --class-path dependency.jar app.jar
~~~

Khi dependency được resolve, lệnh không in missing dependency.

Một chi tiết quan trọng cho CI: jdeps có thể trả exit code 0 dù --missing-deps in ra dependency không tìm thấy. Vì vậy, nếu chính sách build yêu cầu không có missing dependency, pipeline phải kiểm tra nội dung output hoặc dùng bước kiểm tra có quy tắc fail rõ ràng. Không chỉ dựa vào exit code.

Không dùng --ignore-missing-deps để che lỗi dependency trong build bình thường. Tùy chọn này chỉ hữu ích khi cố ý phân tích một phần artifact và đã biết rằng một số dependency không có trong tập phân tích. Ghi rõ lý do khi dùng nó.

--missing-deps có giới hạn với một số filter như package, regex và summary. Kiểm tra jdeps --help trước khi ghép option.

## 11. Tìm JDK internal API bằng --jdk-internals

JDK internal API là các package/class nội bộ không được bảo đảm tương thích như Java SE API công khai. Phụ thuộc vào chúng có thể khiến ứng dụng lỗi khi nâng JDK, do module encapsulation, thay đổi implementation hoặc loại bỏ API.

Ví dụ source cố ý dùng sun.misc.Unsafe:

~~~java
package demo;

import sun.misc.Unsafe;

public final class UnsafeUse {
    private static Unsafe unsafe;

    public static void main(String[] args) {
        System.out.println(unsafe == null);
    }
}
~~~

Compile trên JDK có cung cấp API này có thể phát warning về proprietary/internal API. Sau đó đóng gói class vào unsafe.jar và chạy:

~~~powershell
jdeps --jdk-internals unsafe.jar
~~~

Output minh họa từ JDK 24.0.2:

~~~text
unsafe.jar -> jdk.unsupported
   demo.UnsafeUse -> sun.misc.Unsafe JDK internal API (jdk.unsupported)
~~~

jdeps còn đưa ra cảnh báo rằng JDK internal APIs không được hỗ trợ và có thể bị thay đổi hoặc loại bỏ. sun.misc.Unsafe được gắn với module jdk.unsupported; việc class vẫn compile hoặc module có tồn tại không có nghĩa API này là hợp đồng ổn định.

Một số hướng thay thế tùy mục đích:

- Dùng VarHandle cho thao tác truy cập biến và bộ nhớ có semantics được chuẩn hóa.
- Dùng java.lang.invoke cho method handle và dynamic invocation.
- Dùng ByteBuffer hoặc API chuẩn cho thao tác buffer.
- Dùng concurrency/atomic API chuẩn thay cho primitive nội bộ nếu phù hợp.

Không có một thay thế duy nhất cho mọi cách dùng Unsafe. Phân tích thao tác thực tế và chọn API công khai phù hợp.

--jdk-internals là chế độ chuyên biệt; theo help của JDK 24, không dùng cùng -p, -e hoặc -s. Nó phân tích class trong input và classpath, trừ khi giới hạn bằng -include. Với CI, cần kiểm tra cả output vì công cụ có thể in cảnh báo mà vẫn trả exit code 0.

## 12. Phân tích API công khai bằng --api-only

--api-only giới hạn phân tích vào dependency xuất hiện trong public/protected API của public class, ví dụ:

- Kiểu field public/protected.
- Kiểu tham số method.
- Kiểu trả về.
- Checked exception được khai báo.
- Các kiểu khác xuất hiện trong signature công khai.

~~~powershell
jdeps --api-only -verbose:class app.jar
~~~

Chế độ này hữu ích khi thiết kế thư viện hoặc module API: dependency nào trở thành một phần của public contract? Một dependency chỉ được dùng bên trong implementation có thể có ý nghĩa khác với dependency xuất hiện trong public signature.

--api-only không phải kiểm tra API compatibility đầy đủ. Nó chỉ giới hạn phạm vi dependency tĩnh được xem xét; cần kết hợp compiler/API checks, Javadoc, module review và compatibility tests.

## 13. Tạo sơ đồ dependency bằng DOT

Để lưu dependency graph:

~~~powershell
jdeps --dot-output reports\jdeps app.jar
~~~

jdeps tạo file DOT trong thư mục đích. Với JAR mẫu, các file được tạo gồm:

~~~text
app.jar.dot
summary.dot
~~~

Có thể dùng Graphviz để render:

~~~powershell
dot -Tpng reports\jdeps\summary.dot -o reports\jdeps\summary.png
~~~

Sơ đồ giúp nhìn thấy package/module liên kết với nhau, tìm cụm package phụ thuộc chéo và xác định dependency bất ngờ. Với dự án nhiều module, dùng graph để trao đổi kiến trúc và tìm hướng tách module.

DOT chỉ là một biểu diễn của kết quả phân tích tĩnh. Nếu graph quá lớn, lọc package/class hoặc phân tích theo từng module trước khi render để sơ đồ dễ đọc.

## 14. Phân tích module và JPMS

Java Platform Module System mô tả dependency tường minh trong module-info.java. Module khai báo các module cần đọc bằng requires, package công khai bằng exports, và service bằng uses/provides.

Một module descriptor đơn giản:

~~~java
module com.example.app {
    requires java.sql;
    requires java.net.http;
    exports com.example.app.api;
}
~~~

Phân tích module trên module path:

~~~powershell
jdeps --module-path mods --module com.example.app
~~~

--module chỉ định module gốc cần phân tích. Module path phải chứa các module mà công cụ cần resolve.

Dùng --check để xem module descriptor và dependency graph sau khi phân tích:

~~~powershell
jdeps --check com.example.app --module-path mods
~~~

Option này giúp phát hiện dependency module, graph sau khi loại bỏ cạnh suy ra và một số qualified export không còn được sử dụng. Đọc output cùng module-info.java và cấu hình module path để hiểu vì sao module được yêu cầu.

## 15. Sinh module-info.java cho JAR chưa modular

Với JAR truyền thống chưa có module-info.class, jdeps có thể đề xuất module descriptor:

~~~powershell
jdeps --generate-module-info generated-modules dependency.jar
~~~

Với thư viện cần open module:

~~~powershell
jdeps --generate-open-module generated-modules dependency.jar
~~~

Công cụ tạo module-info.java trong thư mục đích dựa trên dependency tĩnh mà nó phát hiện. Đây là điểm khởi đầu để chuyển thư viện sang JPMS, không phải descriptor production hoàn chỉnh.

Trước khi dùng descriptor được sinh, review:

- Tên module có ổn định và phù hợp quy ước không.
- Package nào cần exports.
- Dependency nào cần requires transitive.
- Có split package giữa các JAR không.
- Service provider có cần uses hoặc provides không.
- Framework có dùng reflection cần opens không.
- API public có làm dependency trở thành contract không.
- Module có phụ thuộc JDK internal API không.

--generate-module-info và --generate-open-module có giới hạn kết hợp với một số option, chẳng hạn --dot-output và --class-path. Xem help của JDK hiện tại trước khi ghép nhiều chế độ.

## 16. Phân tích multi-release JAR

Multi-release JAR có thể chứa nhiều phiên bản class trong cùng archive, ví dụ class gốc và implementation riêng trong META-INF/versions/17/.

Dùng --multi-release để chọn version cần phân tích:

~~~powershell
jdeps --multi-release 17 --list-deps library.jar
~~~

Có thể chỉ định base để phân tích lớp cơ sở:

~~~powershell
jdeps --multi-release base library.jar
~~~

Version được chỉ định phải là base hoặc số nguyên từ 9 trở lên. Nếu thư viện có implementation khác nhau theo Java release, kết quả phân tích có thể khác tùy version. Phải chọn đúng runtime mục tiêu của sản phẩm.

Không phân tích multi-release JAR mà không ghi nhận version đang dùng, nếu kết quả được lưu làm bằng chứng cho release.

## 17. Tìm dependency ngược bằng --inverse

Thông thường jdeps hiển thị một artifact phụ thuộc vào những gì. --inverse trả lời câu hỏi ngược: những artifact nào trực tiếp hoặc gián tiếp phụ thuộc vào package/module/class đang quan tâm?

Ví dụ:

~~~powershell
jdeps --inverse --require java.sql --recursive app.jar
~~~

Hoặc tìm dependency ngược theo package:

~~~powershell
jdeps --inverse --package sun.misc --recursive "lib/*"
~~~

--inverse cần đi kèm filter phù hợp như --require, --package hoặc --regex. Dùng nó khi cần tìm module nào sẽ bị ảnh hưởng nếu loại bỏ hoặc thay đổi một dependency.

## 18. Tự động hóa kiểm tra trong CI

Một pipeline có thể chạy các bước sau sau khi package:

~~~bash
jdeps --version
jdeps -summary app.jar
jdeps --list-deps --class-path 'lib/*' app.jar
jdeps --missing-deps --class-path 'lib/*' app.jar
jdeps --jdk-internals --class-path 'lib/*' app.jar
~~~

Đối với policy nghiêm ngặt, lưu output và kiểm tra nội dung:

~~~bash
missing="$(jdeps --missing-deps --class-path 'lib/*' app.jar 2>&1)"
if [[ -n "$missing" ]]; then
  printf '%s\n' "$missing" >&2
  exit 1
fi

internals="$(jdeps --jdk-internals --class-path 'lib/*' app.jar 2>&1)"
if [[ -n "$internals" ]]; then
  printf '%s\n' "$internals" >&2
  exit 1
fi
~~~

Ví dụ trên coi mọi output từ hai chế độ đó là cần review. Với dự án có ngoại lệ đã được phê duyệt, thay bằng parser/policy rõ ràng và allowlist có owner; không lọc bằng cách bỏ qua mọi output.

PowerShell có thể lưu output và kiểm tra tương tự:

~~~powershell
$missing = & jdeps --missing-deps --class-path 'lib/*' app.jar 2>&1
if ($missing) {
    $missing
    throw 'Missing dependencies detected by jdeps.'
}

$internals = & jdeps --jdk-internals --class-path 'lib/*' app.jar 2>&1
if ($internals) {
    $internals
    throw 'JDK internal API references detected by jdeps.'
}
~~~

Với PowerShell, hãy chạy trong đúng thư mục artifact và kiểm tra $LASTEXITCODE sau native command khi cần. Các ví dụ trên kiểm tra nội dung diagnostic; nên ghi lại cả output và exit code để phân biệt lỗi thực thi jdeps với kết quả phân tích có cảnh báo.

Không chạy --jdk-internals trên mọi thư viện JDK hoặc toàn bộ classpath khổng lồ nếu chỉ muốn đánh giá artifact của ứng dụng. Giới hạn input và classpath tới đúng phạm vi để output dễ review.

## 19. Những giới hạn của phân tích tĩnh

jdeps chỉ nhìn thấy dependency mà nó có thể suy ra từ class file và metadata. Một số trường hợp cần kiểm tra bổ sung:

- Reflection với tên class được tạo từ chuỗi.
- Class.forName() với giá trị lấy từ config hoặc database.
- Service loading và plugin được phát hiện lúc runtime.
- Dependency được tải động từ URL hoặc thư mục ngoài.
- JNI/native library và file cấu hình native.
- Bytecode được sinh hoặc biến đổi lúc chạy.
- Code path chỉ chạy trong production data hoặc feature flag.
- Module/package được mở bằng command-line flags.
- Dependency được thêm bởi container, application server hoặc framework.

Do đó, không có dependency nào được jdeps liệt kê không đồng nghĩa ứng dụng không cần dependency runtime. Kiểm tra cấu hình triển khai, service descriptor, reflection config, integration test và smoke test.

jdeps cũng không đánh giá license, CVE, chất lượng dependency, hiệu năng hay tính đúng đắn nghiệp vụ. Dùng công cụ chuyên biệt cho các yêu cầu đó.

## 20. Lỗi thường gặp khi chạy jdeps

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| not found | Thiếu JAR trên classpath/module path | Bổ sung đúng dependency và chạy lại |
| Không thấy dependency bắc cầu | Chưa bật recursive analysis | Dùng -R/--recursive |
| Output quá dài | Đang xem class-level hoặc không filter | Dùng -summary, package filter hoặc --include |
| Không resolve module | Module path thiếu module hoặc descriptor sai | Kiểm tra --module-path, module name và module-info |
| --jdk-internals báo API nội bộ | Source/dependency dùng JDK internal API | Tìm API chuẩn thay thế hoặc cô lập ngoại lệ |
| Không có output từ --missing-deps | Không phát hiện missing dependency trong phạm vi đã phân tích | Xác nhận classpath và phạm vi đầu vào |
| Không thấy class được nạp động | Dependency chỉ xuất hiện qua reflection/config | Bổ sung kiểm tra runtime và cấu hình |
| Kết quả multi-release khác nhau | Đang phân tích version khác | Chỉ định --multi-release phù hợp |
| JAR mới không phân tích được | jdeps quá cũ với class-file version mới | Dùng jdeps từ JDK tương thích |
| Sơ đồ DOT quá lớn | Quá nhiều class/package | Lọc theo package/module hoặc phân tích từng artifact |

Nếu jdeps báo missing dependency nhưng exit code vẫn 0, hãy kiểm tra diagnostic output. Đừng coi exit code 0 là bằng chứng duy nhất cho một dependency graph hoàn chỉnh.

## 21. Quy trình phân tích một artifact trước release

Một quy trình có thể dùng trong pull request hoặc release review:

1. Build artifact từ source sạch.
2. Ghi lại JDK, jdeps, Maven/Gradle và version dependency.
3. Chạy -summary để xem tổng quan.
4. Chạy -verbose:package hoặc -verbose:class khi cần truy vết.
5. Chạy --missing-deps với đúng classpath/module path.
6. Chạy --jdk-internals trên artifact của ứng dụng.
7. Chạy --list-deps và --print-module-deps nếu cần module inventory.
8. Nếu chuyển JPMS, kiểm tra module graph và review module descriptor được đề xuất.
9. Nếu dùng multi-release JAR, chỉ định release cần phân tích.
10. Chạy unit/integration/smoke test trên runtime tối thiểu được hỗ trợ.
11. Lưu report, command, tool version và quyết định xử lý warning.
12. Review lại kết quả khi nâng JDK hoặc dependency lớn.

Mỗi report nên gắn với commit/artifact cụ thể. Nếu chỉ lưu một file jdeps.txt không có version, command và commit, người khác khó biết report còn đại diện cho build nào.

## 22. Checklist jdeps

- [ ] Đã xác định artifact hoặc thư mục class cần phân tích.
- [ ] jdeps version tương thích với class-file version đầu vào.
- [ ] Đã cung cấp classpath/module path đầy đủ.
- [ ] Đã xem summary trước khi cần phân tích chi tiết.
- [ ] Đã chọn package-level hoặc class-level đúng mục đích.
- [ ] Đã dùng recursive analysis khi cần dependency bắc cầu.
- [ ] Đã kiểm tra missing dependencies và diagnostic output.
- [ ] Đã kiểm tra JDK internal API.
- [ ] Đã xem module dependencies nếu cần tạo runtime image.
- [ ] Đã review module-info.java được sinh tự động trước khi dùng.
- [ ] Đã chỉ định multi-release version nếu phân tích multi-release JAR.
- [ ] Đã hiểu giới hạn với reflection, service loading và JNI.
- [ ] Đã kết hợp jdeps với build/test/runtime verification.
- [ ] Đã lưu command, version, artifact và report trong CI.

jdeps giúp nhìn rõ dependency tĩnh của ứng dụng Java, tìm JDK internal API, phát hiện tham chiếu bị thiếu và hỗ trợ thiết kế module. Kết quả chỉ đáng tin khi phân tích đúng artifact với classpath/module path và release mục tiêu. Dùng jdeps như một lớp kiểm chứng trong build/release, rồi xác nhận các dependency động và hành vi thật bằng test trên runtime được hỗ trợ.

## Tài liệu tham khảo

- Oracle Java SE 24 — The jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle Java SE 17 — The jdeps Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Oracle Java SE 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle Java SE 24 — The jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle — JDK Internal APIs and JEP 260: https://openjdk.org/jeps/260
- Oracle Java Platform Module System — Module Dependences: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
