# Quét class directory bằng jdeps

`jdeps` là công cụ phân tích dependency đi kèm JDK. Công cụ có thể nhận một class file, một thư mục chứa các class đã biên dịch hoặc một JAR làm đầu vào. Khi muốn quét toàn bộ output của một dự án Java, hãy truyền **thư mục class** vào cuối lệnh, thường là thư mục như `build/classes` hoặc `target/classes`.

Để xem quan hệ ở cấp class, dùng `-verbose:class`. Để hiện cả dependency trong cùng package hoặc cùng archive, thêm `-filter:none`. Cần phân biệt đường dẫn thư mục đang được phân tích với classpath dùng để phân giải dependency bên ngoài: thư mục đầu vào là đối tượng cần quét, còn `--class-path` cung cấp các class/JAR khác mà bytecode tham chiếu tới.

## 1. Class directory là gì?

Khi biên dịch mã nguồn Java bằng `javac -d`, compiler ghi các tệp `.class` vào một thư mục output và tạo cây thư mục tương ứng với package. Ví dụ:

~~~text
project/
├── src/
│   └── com/acme/
│       ├── app/Main.java
│       ├── service/GreetingService.java
│       └── util/TextFormatter.java
└── build/
    └── classes/
        └── com/acme/
            ├── app/Main.class
            ├── service/GreetingService.class
            └── util/TextFormatter.class
~~~

Trong ví dụ này, `build/classes` là **class directory root**. Nó chứa thư mục gốc của package `com.acme`. Khi quét, truyền `build/classes` làm input. Không truyền riêng `build/classes/com/acme/app` nếu mục tiêu là phân tích toàn bộ output của ứng dụng.

Class directory thường được tạo bởi build tool hoặc lệnh `javac`. Một directory có thể chứa nhiều package, class lồng nhau, class được sinh bởi annotation processor và metadata khác. `jdeps` tập trung phân tích class file; file resource không phải class dependency sẽ không tạo thành cạnh class trong báo cáo.

## 2. Kiểm tra jdeps và cú pháp đầu vào

`jdeps` là công cụ JDK. Kiểm tra công cụ và trợ giúp:

~~~sh
java -version
jdeps --version
jdeps --help
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command jdeps
jdeps --version
~~~

Cú pháp tổng quát:

~~~sh
jdeps [options] <path ...>
~~~

Đường dẫn đầu vào có thể là một tệp `.class`, một directory hoặc một JAR. Ví dụ quét directory:

~~~sh
jdeps build/classes
~~~

Lệnh trên phân tích class file trong directory và in dependency summary theo mặc định. Để xem từng quan hệ chi tiết hơn, hãy chọn mức verbose phù hợp.

Nếu shell không tìm thấy `jdeps`, kiểm tra JDK đã được cài đặt và thư mục `bin` của JDK có trong PATH. Công cụ thường nằm cạnh `java`, `javac` và `javap`.

## 3. Xem dependency ở cấp class

Lệnh cơ bản để quét directory và in dependency class-level:

~~~sh
jdeps -verbose:class build/classes
~~~

Mức `-verbose:class` cho biết class nguồn tham chiếu tới class đích nào. Theo mặc định, chế độ này lọc các dependency trong cùng package. Nếu muốn xem cả các cạnh bị bộ lọc mặc định ẩn, dùng:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

`-filter:none` tắt bộ lọc dependency trong cùng package và cùng archive. Đây là lựa chọn hữu ích khi cần xem toàn bộ cạnh class-level trong directory. Tùy chọn ngắn `-v` tương đương `-verbose:class -filter:none` trong các phiên bản jdeps hiện hành.

Dạng dòng kết quả thường là:

~~~text
source.class -> target.class module-or-archive
~~~

Ví dụ minh họa:

~~~text
com.acme.app.Main -> com.acme.service.GreetingService build/classes
com.acme.service.GreetingService -> com.acme.util.TextFormatter build/classes
com.acme.app.Main -> java.io.PrintStream java.base
~~~

Tên module hoặc archive ở cột cuối phụ thuộc class được phân giải từ đâu. Kết quả thực tế phụ thuộc class file, classpath, module path, phiên bản JDK và bộ lọc. Các dòng trên minh họa cách đọc quan hệ, không phải đầu ra cố định cho mọi dự án.

## 4. Ví dụ hoàn chỉnh: biên dịch và quét một class directory

Tạo ba source file theo cấu trúc:

~~~text
src/
└── com/acme/
    ├── app/Main.java
    ├── service/GreetingService.java
    └── util/TextFormatter.java
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

Biên dịch tất cả class vào một directory:

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

Chạy ứng dụng để kiểm tra:

~~~sh
java -cp build/classes com.acme.app.Main
~~~

Kết quả stdout:

~~~text
Hello, Java dependencies!
~~~

Quét directory ở cấp class:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

Các quan hệ chính cần thấy gồm:

- `com.acme.app.Main` tham chiếu `com.acme.service.GreetingService`.
- `com.acme.service.GreetingService` tham chiếu `com.acme.util.TextFormatter`.
- Các class ứng dụng cũng tham chiếu các class Java SE như `java.lang.String`, `java.lang.System` hoặc `java.io.PrintStream`.

Báo cáo có thể chứa thêm class và cạnh khác do compiler sinh ra. Điều quan trọng là input của jdeps là thư mục `build/classes`, tức root chứa toàn bộ package tree.

## 5. Phân biệt input directory và classpath

Hai vị trí này có mục đích khác nhau:

| Thành phần | Vai trò |
|---|---|
| Đường dẫn ở cuối lệnh, ví dụ `build/classes` | Artifact được phân tích |
| `--class-path` | Nơi tìm class/JAR để phân giải các tham chiếu ngoài input |
| `--module-path` | Nơi tìm module khi phân tích ứng dụng modular |

Ví dụ, ứng dụng trong `build/classes` sử dụng hai thư viện JAR bên ngoài:

~~~sh
jdeps -verbose:class -filter:none \
  --class-path "lib/alpha.jar:lib/beta.jar" \
  build/classes
~~~

Trên Windows, classpath dùng dấu chấm phẩy:

~~~powershell
jdeps -verbose:class -filter:none --class-path "lib\alpha.jar;lib\beta.jar" build/classes
~~~

Trên macOS/Linux, các mục classpath được phân tách bằng dấu hai chấm. Trên Windows, dùng dấu chấm phẩy. Đặt `build/classes` ở cuối vẫn có nghĩa đó là directory đang được phân tích; thư viện JAR ở `--class-path` chỉ giúp công cụ giải quyết các tham chiếu mà class trong directory sử dụng.

Nếu thiếu JAR dependency, jdeps có thể báo `not found` hoặc không phân giải được class. Bổ sung đúng thư viện và chạy lại trước khi kết luận dependency bị thiếu trong sản phẩm.

## 6. Quét directory với các mức báo cáo khác nhau

Không phải lúc nào cũng cần danh sách class-level đầy đủ. Chọn mức báo cáo theo câu hỏi cần trả lời:

| Tùy chọn | Mục đích |
|---|---|
| `-summary` hoặc `-s` | In tóm tắt dependency |
| `-verbose:package` | In dependency ở cấp package |
| `-verbose:class` | In dependency ở cấp class |
| `-v` | In tất cả dependency ở cấp class và tắt lọc package/archive |
| `-filter:none` | Hiện cả dependency trong cùng package/archive |
| `-filter:package` | Lọc dependency trong cùng package; đây là mặc định |
| `-filter:archive` | Lọc dependency trong cùng archive |
| `-include <regex>` | Giới hạn các class được đưa vào phân tích theo biểu thức chính quy |

Ví dụ xem tóm tắt:

~~~sh
jdeps -summary build/classes
~~~

Xem dependency theo package:

~~~sh
jdeps -verbose:package build/classes
~~~

Xem class-level, kể cả cạnh nội bộ package:

~~~sh
jdeps -v build/classes
~~~

Nếu directory có hàng trăm hoặc hàng nghìn class, summary/package-level giúp nhìn tổng quan nhanh. Khi cần tìm class nào tham chiếu một class khác, dùng class-level.

Bộ lọc chỉ thay đổi nội dung báo cáo, không sửa class file và không xóa dependency khỏi chương trình. Nếu một cạnh không xuất hiện, hãy kiểm tra xem bộ lọc có đang loại nó hay không trước khi kết luận không có quan hệ.

## 7. Giới hạn phạm vi quét trong class directory

Nếu directory lớn, có thể chỉ muốn phân tích một nhóm class. Tùy chọn `-include` nhận regular expression để giới hạn class được phân tích. Ví dụ:

~~~sh
jdeps -verbose:class -filter:none -include "com\.acme\.app\..*" build/classes
~~~

Mẫu regular expression cần khớp tên class theo định dạng mà jdeps báo cáo. Dùng dấu chấm được escape khi muốn biểu diễn dấu chấm package theo nghĩa đen. Hãy kiểm tra output sau khi lọc để xác nhận đúng nhóm class được giữ lại.

Có thể dùng tùy chọn `--package` để lọc dependency theo package:

~~~sh
jdeps -verbose:class --package com.acme.service build/classes
~~~

`--package` lọc các dependency phù hợp với package được chỉ định; nó không thay thế đường dẫn input directory. Nếu cần cả class nguồn cụ thể và dependency đích, kết hợp bộ lọc class với mức verbose và đọc output cẩn thận.

Không nên áp dụng bộ lọc quá sớm khi đang kiểm kê dependency toàn bộ. Hãy chạy một lượt đầy đủ với `-filter:none` để hiểu tập cạnh, sau đó thu hẹp phạm vi để điều tra.

## 8. Phân tích dependency đệ quy

Khi chỉ quét directory, jdeps phân tích các class trong directory đó và dependency được tham chiếu. Nếu muốn tiếp tục theo các dependency runtime đã phân giải để xem chuỗi phụ thuộc bắc cầu, dùng `-R` hoặc `--recursive`:

~~~sh
jdeps -R -verbose:class --class-path "lib/alpha.jar:lib/beta.jar" build/classes
~~~

`-R` yêu cầu phân tích đệ quy và tự hàm ý `-filter:none`. Công cụ sẽ tiếp tục duyệt các dependency runtime có thể phân giải. Kết quả có thể lớn hơn đáng kể vì bao gồm các class thuộc thư viện ngoài.

Dùng phân tích đệ quy khi cần trả lời câu hỏi như “thư viện mà class này dùng còn phụ thuộc vào những thư viện nào?”. Với câu hỏi chỉ về tham chiếu trực tiếp trong directory, bắt đầu bằng lệnh không đệ quy thường dễ hiểu hơn.

Phân tích đệ quy vẫn là phân tích tĩnh. Nó không chứng minh mọi dependency đều được nạp hoặc thực thi trong mọi lần chạy.

## 9. Tìm dependency bị thiếu trong class directory

Có thể yêu cầu jdeps tìm class dependency không được phân giải:

~~~sh
jdeps --missing-deps --class-path "lib/alpha.jar:lib/beta.jar" build/classes
~~~

Lệnh này kiểm tra các dependency của input và báo những tham chiếu không tìm thấy trong class directory đầu vào hoặc classpath được cung cấp. Tùy chọn `--missing-deps` không dùng cùng các bộ lọc `-p`, `-e` hoặc `-s` theo CLI help của JDK hiện hành.

Khi có missing dependency, kiểm tra lần lượt:

1. JAR cần thiết có thực sự tồn tại trong thư mục dependency không.
2. Đường dẫn classpath có đúng và dùng dấu phân tách của hệ điều hành không.
3. JAR có chứa đúng package/class mà bytecode tham chiếu không.
4. Dependency có đúng phiên bản tương thích với ứng dụng không.
5. Class có được cung cấp động bởi container, application server hoặc plugin system không.

Tùy chọn `--ignore-missing-deps` cho phép bỏ qua một số dependency thiếu trong những thao tác phân tích phù hợp. Bỏ qua cảnh báo không sửa được classpath và không chứng minh ứng dụng sẽ chạy thành công.

## 10. Kiểm tra JDK internal API từ class directory

Có thể quét các tham chiếu tới API nội bộ của JDK:

~~~sh
jdeps --jdk-internals build/classes
~~~

Tùy chọn này giúp phát hiện class trong directory tham chiếu tới package nội bộ như `sun.*` hoặc `com.sun.*`. Những API này không được bảo đảm ổn định như Java SE public API và có thể thay đổi hoặc bị giới hạn quyền truy cập giữa các phiên bản JDK.

Nếu kết quả có cảnh báo:

- Xác định class trong ứng dụng tạo tham chiếu.
- Tìm API công khai được Java SE hoặc thư viện hỗ trợ cung cấp.
- Kiểm tra hướng dẫn migration của phiên bản JDK đích.
- Nâng cấp thư viện ngoài nếu thư viện đó phụ thuộc internal API.
- Chỉ cân nhắc `--add-exports` như biện pháp chuyển tiếp khi đã đánh giá rủi ro.

## 11. Class directory modular và module path

Nếu directory chứa class của một module, nó có thể có `module-info.class`. Khi phân tích modular application, cung cấp module path:

~~~sh
jdeps --module-path mods -verbose:class build/modules/com.acme.app
~~~

Để in danh sách module dependency:

~~~sh
jdeps --module-path mods --print-module-deps build/modules/com.acme.app
~~~

`--module-path` cho jdeps biết nơi tìm các module phụ thuộc. Nó khác classpath: module path chứa module được phân giải theo JPMS, còn classpath chứa class/JAR theo cơ chế classpath truyền thống.

Nếu directory là output của module, hãy bảo đảm cấu trúc và module descriptor còn nguyên vẹn. Khi cần phân tích nhiều module, dùng đúng module path và xác định rõ module nào là đối tượng phân tích.

## 12. Giới hạn của quét class directory

jdeps đọc tham chiếu có thể nhận biết trong class file; công cụ không chạy ứng dụng và không quan sát mọi hành vi runtime. Một số dependency có thể được quyết định ngoài bytecode:

- **Reflection**: tên class được ghép từ chuỗi rồi nạp bằng `Class.forName`.
- **Service loading**: provider được khai báo trong metadata hoặc cấu hình và được nạp động.
- **Configuration/resource**: file XML, JSON, properties hoặc script chứa tên class hay tên thư viện.
- **Dependency injection/framework**: framework quét classpath rồi tạo đối tượng theo annotation hoặc cấu hình.
- **JNI/native library**: class gọi mã native hoặc tải thư viện hệ điều hành.
- **Custom class loader/plugin**: class được tải từ thư mục plugin, mạng, database hoặc nguồn động.

Vì vậy, kết quả quét directory không thay thế kiểm thử tích hợp, kiểm tra runtime hoặc danh sách dependency do build tool quản lý. Khi ứng dụng dùng reflection, service provider hoặc plugin, hãy đối chiếu kết quả với cấu hình và log của tiến trình thực tế.

Một cạnh dependency cũng không đồng nghĩa class đích chắc chắn được gọi trong một lần chạy. `jdeps` cho biết quan hệ tham chiếu tĩnh, không phải call graph hoặc execution trace.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jdeps: command not found` | Chưa cài JDK hoặc PATH thiếu JDK bin | Kiểm tra `JAVA_HOME`, PATH và `jdeps --version` |
| Báo cáo không có class mong đợi | Truyền nhầm directory hoặc directory chưa chứa class file mới | Kiểm tra build output và truyền đúng class directory root |
| Không thấy cạnh trong cùng package | Bộ lọc mặc định ẩn dependency nội bộ package | Dùng `-filter:none` |
| Có `not found` | Thiếu JAR hoặc classpath sai | Bổ sung dependency vào `--class-path` |
| Chỉ thấy package summary | Đang dùng `-summary` hoặc `-verbose:package` | Dùng `-verbose:class` |
| Kết quả quá dài | Quét nhiều class hoặc bật recursive | Thu hẹp bằng `-include` hoặc bỏ `-R` |
| Không thấy dependency reflection/plugin | Tham chiếu được tạo động, không hiện trực tiếp trong bytecode | Kiểm tra cấu hình, service metadata và log runtime |
| Module dependency không phân giải | Thiếu hoặc sai module path | Cung cấp `--module-path` và kiểm tra module descriptor |

## 14. Quy trình quét class directory

Khi cần phân tích output của một dự án Java, hãy làm theo thứ tự:

1. Build dự án để tạo class directory mới nhất.
2. Xác định đúng root chứa package tree, ví dụ `build/classes` hoặc `target/classes`.
3. Kiểm tra phiên bản công cụ bằng `jdeps --version`.
4. Bắt đầu bằng `jdeps -verbose:class -filter:none <class-directory>`.
5. Bổ sung `--class-path` nếu class tham chiếu dependency bên ngoài.
6. Dùng `--missing-deps` để tìm class chưa phân giải.
7. Dùng `-R` khi cần theo dõi dependency bắc cầu.
8. Dùng `--jdk-internals` để kiểm tra tham chiếu JDK internal API.
9. Với ứng dụng modular, cung cấp `--module-path`.
10. Đối chiếu báo cáo tĩnh với reflection, service loading, plugin và kiểm thử runtime.

### Checklist

- [ ] Directory đầu vào là output đã biên dịch, không phải thư mục source.
- [ ] Đã truyền class directory root chứa cây package.
- [ ] Đã dùng `-verbose:class` để xem quan hệ class.
- [ ] Đã dùng `-filter:none` khi cần cả cạnh nội bộ package/archive.
- [ ] Đã cung cấp classpath/module path cho dependency ngoài.
- [ ] Đã kiểm tra missing dependency nếu có.
- [ ] Đã chỉ dùng recursive khi cần phân tích bắc cầu.
- [ ] Đã xem xét giới hạn của reflection, service loading và plugin.
- [ ] Đã xác minh đúng build output đang được triển khai.

`jdeps <class-directory>` cho phép phân tích trực tiếp các class file trong output của dự án. Kết hợp `-verbose:class`, bộ lọc phù hợp và classpath đầy đủ, bạn có thể xác định class nào tham chiếu class nào, phát hiện dependency thiếu và hiểu cấu trúc phụ thuộc trước khi kiểm thử hoặc triển khai ứng dụng.