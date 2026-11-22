# Phân tích dependency ở cấp class bằng jdeps

`jdeps` là công cụ phân tích dependency đi kèm JDK. Công cụ đọc class file, thư mục class hoặc JAR để xác định những class/package/module mà mã bytecode tham chiếu. Khi cần xem class nào phụ thuộc class nào, tùy chọn quan trọng là `-verbose:class`.

Phân tích dependency ở cấp class giúp lần theo quan hệ giữa các class trong ứng dụng, phát hiện phụ thuộc ngoài dự kiến, tìm class không phân giải được và hiểu vì sao một thư viện cần có trên classpath hoặc module path. Kết quả là dữ liệu phân tích tĩnh từ bytecode; `jdeps` không chạy chương trình và không tạo call graph ở cấp phương thức.

## 1. Dependency class là gì?

Một class có dependency tới class khác khi bytecode của nó tham chiếu tới kiểu hoặc thành phần thuộc class đó. Ví dụ, class `Main` tạo đối tượng `GreetingService`, gọi phương thức của nó và sử dụng `String`. Những tham chiếu này có thể xuất hiện trong constant pool, descriptor, superclass, interface, annotation hoặc các cấu trúc khác của class file.

Ví dụ quan hệ giữa ba class:

~~~text
com.acme.app.Main
        |
        v
com.acme.service.GreetingService
        |
        v
com.acme.util.TextFormatter
~~~

Trong ví dụ trên, `Main` phụ thuộc `GreetingService`; `GreetingService` phụ thuộc `TextFormatter`. Đây là quan hệ class-level. Nó cho biết một class có tham chiếu tới class khác, không cho biết toàn bộ chuỗi gọi hàm, thứ tự gọi hoặc số lần gọi khi chương trình chạy.

Cần phân biệt:

- **Dependency class**: quan hệ tham chiếu giữa các class.
- **Dependency package**: quan hệ giữa các package chứa class.
- **Dependency module**: quan hệ ở mức module, thường gắn với Java Platform Module System (JPMS).
- **Call graph**: quan hệ lời gọi phương thức; `jdeps` không phải công cụ tạo call graph đầy đủ.

Import trong source code không phải là báo cáo dependency chính xác. Một import không được sử dụng có thể không tạo tham chiếu trong bytecode; ngược lại, mã có thể dùng tên class đầy đủ mà không có câu lệnh import. `jdeps` phân tích class file đã biên dịch, nên kết quả phản ánh tham chiếu trong artifact.

## 2. Cài đặt và kiểm tra jdeps

`jdeps` là công cụ của JDK. Hãy kiểm tra JDK đang được dùng và phiên bản công cụ:

~~~sh
java -version
jdeps --version
jdeps --help
~~~

Nếu shell không tìm thấy `jdeps`, kiểm tra thư mục `bin` của JDK có nằm trong PATH hay không. `jdeps` thường nằm cạnh `java`, `javac` và `javap` trong thư mục JDK.

Trên Windows PowerShell, có thể kiểm tra đường dẫn công cụ:

~~~powershell
Get-Command jdeps
jdeps --version
~~~

Trên macOS/Linux:

~~~sh
command -v jdeps
jdeps --version
~~~

Nên dùng `jdeps` từ JDK tương ứng với quy trình build hoặc runtime cần phân tích. Phiên bản công cụ có thể ảnh hưởng tới khả năng hiểu class-file version, module và các tùy chọn mới.

## 3. Xem dependency ở cấp class với -verbose:class

Cú pháp cơ bản:

~~~sh
jdeps -verbose:class path/to/classes
~~~

Đối với một thư mục chứa class file:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

Đối với một JAR:

~~~sh
jdeps -verbose:class -filter:none app.jar
~~~

`-verbose:class` yêu cầu hiển thị dependency ở cấp class. `-filter:none` tắt bộ lọc dependency để kết quả không loại bỏ các cạnh theo bộ lọc mặc định. Điều này hữu ích khi muốn kiểm tra đầy đủ quan hệ giữa các class trong cùng package hoặc cùng archive.

Dạng kết quả thường có cấu trúc:

~~~text
source.class -> target.class module-or-archive
~~~

Ví dụ minh họa:

~~~text
com.acme.app.Main -> com.acme.service.GreetingService build/classes
com.acme.service.GreetingService -> com.acme.util.TextFormatter build/classes
com.acme.app.Main -> java.io.PrintStream java.base
~~~

Tên archive hoặc nhãn module ở cột cuối phụ thuộc artifact và phiên bản JDK. Kết quả thực tế còn phụ thuộc source đã biên dịch, classpath, module path và bộ lọc. Không nên dựa vào một chuỗi đầu ra cố định khi viết script; hãy đọc kết quả theo ý nghĩa các cột.

## 4. Ví dụ hoàn chỉnh với nhiều class

Tạo cấu trúc source:

~~~text
src/
└── com/acme/
    ├── app/
    │   └── Main.java
    ├── service/
    │   └── GreetingService.java
    └── util/
        └── TextFormatter.java
~~~

`TextFormatter.java`:

~~~java
package com.acme.util;

public class TextFormatter {
    public String format(String name) {
        return "Hello, " + name + " dependencies!";
    }
}
~~~

`GreetingService.java`:

~~~java
package com.acme.service;

import com.acme.util.TextFormatter;

public class GreetingService {
    private final TextFormatter formatter = new TextFormatter();

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`Main.java`:

~~~java
package com.acme.app;

import com.acme.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));
    }
}
~~~

Biên dịch các class vào thư mục output:

~~~sh
mkdir -p build/classes
javac -d build/classes \
  src/com/acme/util/TextFormatter.java \
  src/com/acme/service/GreetingService.java \
  src/com/acme/app/Main.java
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/classes | Out-Null
javac -d build/classes src/com/acme/util/TextFormatter.java src/com/acme/service/GreetingService.java src/com/acme/app/Main.java
~~~

Chạy ứng dụng:

~~~sh
java -cp build/classes com.acme.app.Main
~~~

Kết quả stdout:

~~~text
Hello, Java dependencies!
~~~

Phân tích các class:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

Bạn sẽ thấy các quan hệ chính giữa `com.acme.app.Main`, `com.acme.service.GreetingService` và `com.acme.util.TextFormatter`. Ngoài các class của ứng dụng, kết quả có thể bao gồm tham chiếu tới class Java SE như `java.lang.String`, `java.lang.System` hoặc `java.io.PrintStream`.

Lệnh chạy ứng dụng chỉ cần classpath root `build/classes`. Không đặt classpath trỏ thẳng vào một thư mục package con nếu muốn dùng tên class đầy đủ.

## 5. Phân tích JAR và dependency ngoài

`jdeps` có thể phân tích JAR đã đóng gói:

~~~sh
jdeps -verbose:class -filter:none app.jar
~~~

Nếu JAR tham chiếu class thuộc thư viện khác, hãy cung cấp các dependency để công cụ phân giải được:

~~~sh
jdeps -verbose:class --class-path "lib/alpha.jar:lib/beta.jar" app.jar
~~~

Trên Windows, dấu phân tách classpath là dấu chấm phẩy:

~~~powershell
jdeps -verbose:class --class-path "lib\alpha.jar;lib\beta.jar" app.jar
~~~

Trên macOS/Linux, dấu phân tách là dấu hai chấm. Nếu thiếu một dependency, kết quả có thể đánh dấu `not found` hoặc báo cảnh báo tùy tình huống. Hãy bổ sung đúng JAR vào classpath phân tích rồi chạy lại để biết dependency có thể được phân giải hay không.

Một JAR có thể chứa nhiều package và nhiều class. `-verbose:class` giúp xác định class cụ thể tạo tham chiếu tới class khác, hữu ích hơn báo cáo package khi cần truy nguyên một phụ thuộc trực tiếp.

Cần kiểm tra đúng artifact. Một class trong thư mục build có thể khác class cùng tên nằm trong JAR cũ. Nếu kết quả không khớp source hiện tại, hãy xác minh đường dẫn JAR/thư mục, build output và classpath mà công cụ đang đọc.

## 6. Bộ lọc và mức chi tiết

`jdeps` có các mức báo cáo khác nhau:

| Tùy chọn | Kết quả |
|---|---|
| `-summary` hoặc `-s` | Tóm tắt dependency thay vì liệt kê từng cạnh class |
| `-verbose:package` | Dependency ở cấp package |
| `-verbose:class` | Dependency ở cấp class |
| `-verbose` | Chế độ chi tiết class; thường kết hợp với bộ lọc phù hợp |
| `-filter:none` | Không áp dụng bộ lọc dependency |
| `-filter:package` | Lọc các dependency trong cùng package |
| `-filter:archive` | Lọc các dependency trong cùng archive |

Ví dụ, so sánh dependency ở cấp package và class:

~~~sh
jdeps -verbose:package app.jar
jdeps -verbose:class -filter:none app.jar
~~~

Báo cáo package phù hợp để xem kiến trúc tổng thể. Báo cáo class phù hợp khi cần biết chính xác class nguồn và class đích của từng quan hệ.

Bộ lọc làm thay đổi những cạnh được hiển thị, không sửa bytecode và không xóa dependency khỏi artifact. Nếu cần kiểm tra toàn diện, hãy chạy lại với `-filter:none` trước khi kết luận không có phụ thuộc.

## 7. Phân tích đệ quy và dependency bị thiếu

Thông thường, `jdeps` báo cáo dependency của đối tượng được chỉ định. Tùy chọn `-R` hoặc `--recursive` yêu cầu công cụ đi tiếp qua các dependency được phân giải, hữu ích khi muốn xem sâu hơn chuỗi phụ thuộc:

~~~sh
jdeps -R -verbose:class -filter:none --class-path "lib/*" app.jar
~~~

Phân tích đệ quy có thể tạo lượng đầu ra lớn vì công cụ tiếp tục theo các dependency bên ngoài. Dùng khi thực sự cần hiểu chuỗi phụ thuộc mở rộng; với một lỗi trực tiếp, bắt đầu bằng phân tích class-level không đệ quy thường dễ đọc hơn.

Có thể yêu cầu báo cáo dependency bị thiếu:

~~~sh
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Kết quả giúp xác định class mà dependency của ứng dụng tham chiếu nhưng không tìm thấy trong tập đầu vào và classpath đã cung cấp. Nếu cần tiếp tục phân tích dù còn dependency chưa giải quyết, `--ignore-missing-deps` có thể bỏ qua lỗi thiếu trong một số thao tác. Tùy chọn bỏ qua không sửa dependency và không chứng minh ứng dụng có thể chạy.

Khi gặp dependency thiếu, hãy kiểm tra:

1. JAR có thực sự được build hoặc tải về không.
2. Classpath có trỏ đúng vị trí file không.
3. Phiên bản JAR có chứa class mà bytecode yêu cầu không.
4. Class thuộc dependency tùy chọn, profile hoặc module riêng nào.
5. Dependency có được cung cấp lúc chạy bởi container/application server hay không.

## 8. Dependency trên module path

Với ứng dụng Java modular, class được tổ chức trong module có khai báo `module-info.java`. Khi phân tích module, cần cung cấp module path thay vì chỉ classpath:

~~~sh
jdeps --module-path mods -verbose:class app.jar
~~~

Để xem danh sách module mà ứng dụng phụ thuộc:

~~~sh
jdeps --print-module-deps --module-path mods app.jar
~~~

`--module-path` cho `jdeps` biết vị trí module phụ thuộc. `--print-module-deps` in danh sách module cần thiết theo phân tích của công cụ, thường dùng khi chuẩn bị cấu hình runtime image với `jlink`.

Một module có thể chứa nhiều class. Báo cáo module hữu ích cho cấu hình runtime và ranh giới module; báo cáo `-verbose:class` hữu ích khi cần lần theo class cụ thể trong module.

## 9. Phát hiện phụ thuộc vào JDK internal API

Có thể kiểm tra class/JAR có tham chiếu tới API nội bộ của JDK hay không:

~~~sh
jdeps --jdk-internals app.jar
~~~

Kết quả có thể chỉ ra class sử dụng package nội bộ như `sun.*` hoặc `com.sun.*` không được đảm bảo là API Java SE công khai. Những API này có thể thay đổi hoặc bị đóng quyền truy cập qua các phiên bản JDK.

Nếu công cụ báo phụ thuộc internal API:

- Tìm API công khai được Java SE hoặc thư viện hỗ trợ cung cấp.
- Kiểm tra hướng dẫn di trú của JDK đang dùng.
- Cập nhật dependency cũ nếu thư viện bên ngoài dựa vào internal API.
- Không dùng `--add-exports` như giải pháp mặc định lâu dài; chỉ cân nhắc khi đã hiểu rủi ro và có kế hoạch loại bỏ.

## 10. Giới hạn của phân tích tĩnh

`jdeps` phân tích tham chiếu có thể tìm thấy trong class file. Nó không quan sát toàn bộ hành vi runtime. Một số phụ thuộc có thể không xuất hiện rõ trong bytecode:

- **Reflection**: ứng dụng tạo tên class bằng chuỗi rồi gọi `Class.forName`.
- **Service loading**: provider được khai báo trong metadata hoặc cấu hình và được nạp động.
- **Configuration/resource**: file XML, JSON, properties hoặc script chứa tên class hay tên thư viện.
- **JNI/native library**: mã Java tải thư viện native hoặc gọi mã native phụ thuộc thành phần bên ngoài.
- **Dependency injection/framework**: framework quét classpath và tạo đối tượng dựa trên annotation hoặc cấu hình.
- **Class loading tùy biến**: classloader tìm bytecode từ mạng, database, plugin directory hoặc nguồn động.

Do đó, `jdeps` không thay thế kiểm thử tích hợp, kiểm tra runtime hoặc tài liệu dependency của ứng dụng. Khi hệ thống dùng reflection, plugin hoặc service provider, hãy đối chiếu kết quả phân tích với cấu hình và các kịch bản chạy thực tế.

Công cụ cũng không cho biết class nào chắc chắn được thực thi trong một lần chạy. Một tham chiếu trong bytecode không đồng nghĩa đường đi đó luôn được gọi; ngược lại, class được nạp động có thể không xuất hiện trong báo cáo tĩnh.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jdeps: command not found` | JDK chưa được cài hoặc PATH thiếu JDK bin | Kiểm tra `JAVA_HOME`, PATH và `jdeps --version` |
| `not found` trong báo cáo | Thiếu dependency hoặc classpath sai | Bổ sung đúng JAR vào `--class-path` và chạy lại |
| Không thấy cạnh giữa hai class trong cùng package | Bộ lọc loại bỏ dependency trong package/archive | Chạy lại với `-filter:none` |
| Báo cáo chỉ hiện package | Đang dùng `-verbose:package` hoặc summary | Dùng `-verbose:class` |
| Kết quả quá dài | Phân tích đệ quy hoặc archive chứa nhiều dependency | Bỏ `-R`, thu hẹp đầu vào hoặc dùng summary |
| Không thấy dependency được nạp bằng reflection | Tham chiếu không có trong bytecode theo cách `jdeps` nhận diện | Kiểm tra cấu hình, service metadata và log runtime |
| Báo cáo khác với source hiện tại | Đang phân tích class/JAR cũ hoặc sai build output | Xác minh đường dẫn artifact, clean/rebuild và phân tích lại |
| Module dependency không được phân giải | Thiếu module path hoặc chọn sai module | Cung cấp `--module-path` và kiểm tra tên module |

## 12. Quy trình phân tích dependency class

Khi cần tìm class nào phụ thuộc class nào, hãy làm theo thứ tự:

1. Xác định artifact cần phân tích: thư mục class, class file hoặc JAR.
2. Kiểm tra phiên bản công cụ bằng `jdeps --version`.
3. Bắt đầu với `jdeps -verbose:class -filter:none` trên artifact.
4. Bổ sung `--class-path` hoặc `--module-path` để phân giải dependency ngoài.
5. Dùng `--missing-deps` để tìm class chưa phân giải được.
6. Chỉ bật `-R` khi cần truy vết dependency bắc cầu.
7. Dùng `--jdk-internals` để kiểm tra tham chiếu tới JDK internal API.
8. Đối chiếu kết quả với cấu hình reflection, service loading, resource và kiểm thử runtime.
9. Ghi nhận các dependency cần thiết trong build và deployment để artifact chạy đúng môi trường.

### Checklist

- [ ] Đã chọn đúng class directory hoặc JAR.
- [ ] Đã dùng `-verbose:class` để xem quan hệ class-level.
- [ ] Đã hiểu tác động của bộ lọc; dùng `-filter:none` khi cần toàn bộ cạnh.
- [ ] Đã cung cấp classpath/module path cho dependency ngoài.
- [ ] Đã kiểm tra dependency thiếu nếu có cảnh báo.
- [ ] Đã dùng `-R` chỉ khi cần phân tích đệ quy.
- [ ] Đã kiểm tra JDK internal API khi cần.
- [ ] Đã tính tới reflection, service loading và dependency runtime động.
- [ ] Đã xác minh artifact phân tích là bản build mới nhất.

`jdeps -verbose:class` cho biết class nguồn tham chiếu tới class đích nào trong bytecode. Kết hợp đúng classpath, bộ lọc và kiểm tra dependency thiếu sẽ giúp bạn lần theo cấu trúc phụ thuộc của ứng dụng Java, đồng thời nhận biết giới hạn của phân tích tĩnh trước khi đưa ra kết luận về runtime.