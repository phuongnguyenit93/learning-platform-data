# Khai báo lớp provider bằng UTF-8, dòng chú thích và quy tắc trùng lặp

Khi triển khai cơ chế plugin trên **Java classpath**, một class triển khai đúng interface chưa đủ để ứng dụng chủ (host) tìm được nó. **java.util.ServiceLoader** dựa vào tài nguyên khai báo dịch vụ tại đường dẫn **META-INF/services/**. Tệp này có các quy tắc riêng về tên, mã hóa UTF-8, dòng trống, chú thích và khai báo trùng; sai một chi tiết có thể khiến provider không được tìm thấy hoặc gây ServiceConfigurationError khi sử dụng.

Bài này tập trung vào **provider-configuration file trên classpath**, áp dụng cho JAR và thư mục classpath thông thường trong Java 17+. Với *named modules* thuộc JPMS, việc công bố provider chủ yếu dùng chỉ thị provides trong module-info.java và việc tiêu thụ service có chỉ thị uses; đó là một hình thức đăng ký khác.

## 1. Phân biệt service, provider và tệp đăng ký

Giả sử host cần những bộ chuyển đổi văn bản khác nhau. Hợp đồng được định nghĩa trong API chung:

**src/api/demo/spi/Formatter.java**

~~~java
package demo.spi;

public interface Formatter {
    String id();
    String format(String input);
}
~~~

Một lớp demo.plugins.Upper thực thi Formatter là **provider**. Để ServiceLoader tìm nó, trong JAR plugin cần tài nguyên có **đường dẫn đúng như sau**:

~~~text
META-INF/services/demo.spi.Formatter
~~~

Nội dung ban đầu đơn giản là:

~~~text
demo.plugins.Upper
~~~

| Thành phần | Cụ thể | Vai trò |
| --- | --- | --- |
| Service type | demo.spi.Formatter | Interface mà host biết và muốn tìm implementation |
| Tên tệp cấu hình | META-INF/services/demo.spi.Formatter | Xác định service được đăng ký |
| Một dòng cấu hình | demo.plugins.Upper | Tên nhị phân đầy đủ của class provider |
| Lệnh sử dụng | ServiceLoader.load(Formatter.class) | Tạo service loader để khám phá các provider |

Tên file dùng **tên nhị phân đầy đủ của service** với dấu chấm trong package; không phải đường dẫn demo/spi/Formatter, không có đuôi .class, .java, .txt hoặc .properties. Bên trong file, mỗi provider cũng được viết bằng tên nhị phân đầy đủ, thường là package.ClassName.

Tài nguyên này **không phải source Java**. Không thêm từ khóa import, class, new hay ký tự kết thúc câu lệnh Java. ServiceLoader không quét ngẫu nhiên tất cả class có implements Formatter; nó đọc metadata đã công bố.

Một file có thể liệt kê nhiều provider. Nhiều JAR có thể có tài nguyên **cùng tên** cho một service, vì ClassLoader.getResources có thể tìm được nhiều tài nguyên khớp. Class được nhắc đến không nhất thiết nằm trong chính JAR chứa metadata, nhưng class đó phải có thể được class loader thích hợp nạp và phải tương thích với service type.

## 2. Quy tắc UTF-8, comment, khoảng trắng và dòng trống

Xét một provider-configuration file hợp lệ:

~~~text
# Các provider chuyển đổi văn bản

demo.plugins.Upper             # chuyển thành chữ hoa
demo.plugins.Lower             # chuyển thành chữ thường

    demo.plugins.Upper         # xuất hiện lần thứ hai
~~~

ServiceLoader áp dụng các quy tắc cú pháp được quy định cho classpath:

1. **Tệp phải được mã hóa bằng UTF-8.** Văn bản tiếng Việt trong chú thích hợp lệ nếu lưu đúng UTF-8. Việc truyền cờ javac -encoding UTF-8 cho source .java không tự chuyển đổi encoding của resource.
2. **Mỗi dòng dữ liệu chứa một tên class provider.** Tên phải là tên nhị phân Java hợp lệ và được viết đầy đủ, ví dụ demo.plugins.Upper. Không được viết biểu thức new demo.plugins.Upper(), đường dẫn demo/plugins/Upper.class hoặc đặt dấu chấm phẩy ở cuối.
3. **Khoảng trắng và tab ở trước/sau tên được bỏ qua.** Dòng có khoảng trắng thụt vào vẫn chỉ đến cùng provider. Khoảng trắng ở bên trong tên class có thể làm dòng không hợp lệ.
4. **Dòng trắng được bỏ qua.** Dòng trống hoặc chỉ có dấu cách/tab không làm tăng số provider.
5. **Dấu # bắt đầu chú thích.** Tất cả ký tự tính từ dấu # đầu tiên trên dòng đến cuối dòng sẽ bị bỏ qua. Bởi vậy cả dòng chỉ có chú thích và phần chú thích sau tên class đều hợp lệ.
6. **Tên class lặp lại được bỏ qua.** Nếu một provider class được khai báo hai lần trong cùng tệp, hoặc xuất hiện trong nhiều tệp cấu hình của cùng service, ServiceLoader bỏ qua khai báo trùng khi khám phá provider.
7. **Dòng không hợp lệ không được coi như chú thích.** Một dòng sai tên class, sai cú pháp hoặc dẫn tới class không nạp được có thể gây ServiceConfigurationError khi iterator thực sự khám phá provider.

Các dòng sau chỉ minh họa **cú pháp không hợp lệ**; không đặt chúng vào descriptor thật:

~~~text
demo/plugins/Upper.class
new demo.plugins.Upper()
demo.plugins.Upper;
demo.plugins. Upper
~~~

Không nên nghĩ rằng mọi ký tự sau tên provider đều được bỏ qua; chỉ có **khoảng trắng/tab xung quanh tên** và **phần sau dấu #** được phép bỏ qua như đã nêu.

## 3. Lưu tệp UTF-8 đúng cách

Với Gradle hoặc Maven theo cấu trúc Java tiêu chuẩn, đặt tài nguyên tại:

~~~text
src/main/resources/META-INF/services/demo.spi.Formatter
~~~

Sau khi build, hãy kiểm tra trong JAR có mục **META-INF/services/demo.spi.Formatter**. Nếu JAR lại chứa **src/main/resources/META-INF/services/...** hoặc **resources/META-INF/services/...**, tệp đang ở sai vị trí tương đối với classpath root.

**Nên lưu UTF-8 không BOM.** Một dấu byte-order mark UTF-8 ở đầu tệp có thể bị coi là ký tự nằm trong tên provider đầu tiên, gây lỗi định dạng dù tên class trông có vẻ đúng trong editor. Không cần BOM để nhận biết UTF-8.

Trên **Windows PowerShell 5.1**, Set-Content -Encoding UTF8 thường tạo BOM. Khi cần ghi file bằng PowerShell, có thể dùng .NET và chỉ rõ UTF-8 không BOM (thư mục cha phải tồn tại trước):

~~~powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$descriptorText = "# Provider UTF-8" + [Environment]::NewLine +
                  "demo.plugins.Upper" + [Environment]::NewLine

[System.IO.File]::WriteAllText(
    'resources/upper/META-INF/services/demo.spi.Formatter',
    $descriptorText,
    $utf8NoBom
)
~~~

Đoạn này là một **minh họa thao tác ghi resource**; không phải phần bắt buộc để chạy ví dụ ở mục sau nếu bạn đã tạo và lưu các tệp resource bằng editor. Với hệ thống CI, cần bảo đảm bước đóng gói không tự chuyển encoding hay ghép một tệp văn bản theo cách làm hỏng resource.

## 4. Ví dụ Java 17: hai JAR provider, cùng file cấu hình được phát hiện nhiều lần

Ta tạo hai provider khác nhau (Upper và Lower), cố tình khai báo **Upper lặp trong file thứ nhất và lặp lại trong file thứ hai**. Host sẽ duyệt ServiceLoader, sắp xếp kết quả để stdout có thứ tự ổn định, rồi in số provider phát hiện được.

### 4.1. Cấu trúc tệp

~~~text
src/
  api/demo/spi/Formatter.java
  upper/demo/plugins/Upper.java
  lower/demo/plugins/Lower.java
  host/demo/app/Main.java
resources/
  upper/META-INF/services/demo.spi.Formatter
  lower/META-INF/services/demo.spi.Formatter
~~~

Ta đã có source Formatter.java ở mục 1; tạo chính xác ba tệp Java còn lại dưới đây.

### 4.2. Lớp provider chữ hoa

**src/upper/demo/plugins/Upper.java**

~~~java
package demo.plugins;

import demo.spi.Formatter;
import java.util.Locale;

public final class Upper implements Formatter {
    public String id() { return "upper"; }
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**resources/upper/META-INF/services/demo.spi.Formatter** (UTF-8 không BOM):

~~~text
# Chú thích UTF-8: bộ xử lý chữ hoa

demo.plugins.Upper      # tên provider hợp lệ
demo.plugins.Upper      # trùng cùng tệp, bỏ qua
~~~

Hai dòng dữ liệu đều chỉ cùng demo.plugins.Upper. Java sẽ không trả lại hai provider Upper chỉ vì hai dòng đó. Từ sau dấu # là chú thích, không thuộc tên class.

### 4.3. Lớp provider chữ thường

**src/lower/demo/plugins/Lower.java**

~~~java
package demo.plugins;

import demo.spi.Formatter;
import java.util.Locale;

public final class Lower implements Formatter {
    public String id() { return "lower"; }
    public String format(String input) {
        return input.toLowerCase(Locale.ROOT);
    }
}
~~~

**resources/lower/META-INF/services/demo.spi.Formatter** (UTF-8 không BOM):

~~~text
# Cấu hình từ JAR thứ hai
demo.plugins.Lower
demo.plugins.Upper # trùng khác tệp, bỏ qua
~~~

File thứ hai nhắc đến class Upper dù class đó nằm trong upper.jar. Điều này hợp lệ khi upper.jar có trên runtime classpath và class loader có thể nạp class ấy. Nếu bỏ upper.jar nhưng giữ dòng demo.plugins.Upper trong cấu hình của lower.jar, một provider đang được tham chiếu không còn tải được, gây lỗi khi khám phá chứ không đơn giản bị bỏ qua vì là dòng trùng.

### 4.4. Host duyệt provider

**src/host/demo/app/Main.java**

~~~java
package demo.app;

import demo.spi.Formatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<String> lines = new ArrayList<>();
        for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
            lines.add(formatter.id() + "=" + formatter.format("HeLLo"));
        }
        Collections.sort(lines);
        lines.forEach(System.out::println);
        System.out.println("provider count=" + lines.size());
    }
}
~~~

Host chỉ import Formatter; không import Upper hoặc Lower. Collections.sort làm cho kết quả hiển thị không phụ thuộc thứ tự ServiceLoader tìm ra các JAR/tài nguyên. Locale.ROOT ở hai plugin giữ thao tác chữ hoa/chữ thường độc lập locale mặc định của máy.

### 4.5. Lệnh biên dịch, đóng gói và chạy

Chạy từ thư mục chứa src và resources, bằng **PowerShell trên Windows**, với JDK 17 hoặc mới hơn. Các tệp descriptor phải được tạo đúng đường dẫn và lưu UTF-8 không BOM từ trước.

~~~powershell
New-Item -ItemType Directory -Force -Path out/api,out/upper,out/lower,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/demo/spi/Formatter.java
jar --create --file dist/spi.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/upper src/upper/demo/plugins/Upper.java
jar --create --file dist/upper.jar -C out/upper . -C resources/upper META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/lower src/lower/demo/plugins/Lower.java
jar --create --file dist/lower.jar -C out/lower . -C resources/lower META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host src/host/demo/app/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/spi.jar;dist/host.jar;dist/upper.jar;dist/lower.jar" demo.app.Main
~~~

Đối với Linux/macOS, tạo thư mục bằng mkdir -p out/api out/upper out/lower out/host dist và thay dấu phân cách classpath trong lệnh java từ dấu chấm phẩy thành dấu hai chấm. Các lệnh javac và jar với đường dẫn tương đối như trên vẫn dùng được.

**Stdout của chương trình:**

~~~text
lower=hello
upper=HELLO
provider count=2
~~~

Mặc dù có tổng cộng ba dòng tham chiếu Upper qua hai tài nguyên, ServiceLoader chỉ khám phá hai **tên lớp provider phân biệt**: demo.plugins.Upper và demo.plugins.Lower. Do vậy số provider bằng 2. Ví dụ này đã được biên dịch bằng javac --release 17, đóng gói bốn JAR và chạy thực tế với kết quả trên.

Kiểm tra nội dung upper.jar bằng:

~~~powershell
jar tf dist/upper.jar
~~~

Bạn phải thấy ít nhất hai mục sau trong danh sách kết quả:

~~~text
demo/plugins/Upper.class
META-INF/services/demo.spi.Formatter
~~~

Đây là **hai mục cần tìm**, không phải toàn bộ output của jar tf; lệnh thực còn liệt kê các thư mục và META-INF/MANIFEST.MF. Nếu tệp dịch vụ không xuất hiện trong JAR, hãy sửa bước đóng gói resource trước khi kiểm tra code Java.

## 5. Hiểu chính xác quy tắc trùng lặp

ServiceLoader chỉ tự loại **trùng tên nhị phân của class provider trong cùng quá trình khám phá service**, không giải quyết mọi dạng trùng lặp trong hệ plugin.

| Tình huống | Kết quả | Giải thích |
| --- | --- | --- |
| Upper được ghi hai lần trong cùng resource | Không có hai provider Upper | Trùng class name được bỏ qua |
| Upper được ghi trong resource của hai JAR | Không có hai provider Upper trong cùng lượt khám phá | Trùng tên giữa các resource cũng được bỏ qua |
| Upper và Lower là hai class khác nhau | Cả hai có thể được nạp | Khác tên class dù cùng interface |
| Hai class khác nhau cùng trả id() là "upper" | Cả hai vẫn được nạp | id() là quy ước nghiệp vụ, không phải khóa loại trùng của ServiceLoader |
| Duyệt lại cùng một ServiceLoader | Trả lại các provider đã được cache | Không nhân đôi do duyệt iterator lần nữa |
| Tạo một ServiceLoader mới hoặc gọi reload() | Có thể khám phá và khởi tạo lại provider | Không có bảo đảm một instance duy nhất toàn JVM |
| Dùng các class loader khác nhau | Mỗi loader có phạm vi tài nguyên/kiểu nhìn thấy riêng | Không được suy luận trùng toàn hệ thống |

Nếu host muốn id() duy nhất, nó phải có **chính sách phát hiện xung đột**. Ví dụ đoạn code sau dùng **bên trong một method Java**, sau khi import java.util.Map và java.util.HashMap:

~~~java
Map<String, Formatter> byId = new HashMap<>();
for (Formatter provider : ServiceLoader.load(Formatter.class)) {
    Formatter previous = byId.putIfAbsent(provider.id(), provider);
    if (previous != null) {
        throw new IllegalStateException("Duplicate provider id: " + provider.id());
    }
}
~~~

Đoạn này là **minh họa logic thay thế**, không phải chương trình Java độc lập. Nó phát hiện hai lớp provider khác nhau chọn cùng id nghiệp vụ, điều mà ServiceLoader không thể tự đoán. Trong một framework plugin lớn hơn, nên quyết định rõ hành vi khi có id trùng: từ chối, chọn theo priority đã công bố hoặc dùng cấu hình được kiểm soát.

Không hiểu nhầm quy tắc duplicate như cơ chế tự kiểm tra chất lượng. ServiceLoader chỉ bỏ qua các **khai báo cùng tên**; một class provider không hợp lệ vẫn có thể khiến quá trình khám phá thất bại. Cũng không suy ra rằng constructor sẽ chạy ba lần rồi xóa hai instance: provider được nạp và tạo instance **lazily**, còn khai báo trùng bị bỏ qua trong quá trình tìm provider.

## 6. Khi hai JAR cùng đóng góp một resource

Với hai JAR riêng, việc cả hai chứa META-INF/services/demo.spi.Formatter là bình thường. Khi host sử dụng classpath, nhiều resource đó có thể cùng được nhìn thấy.

Nhưng khi build **fat JAR/uber JAR** bằng cách gộp dependency, hai entry cùng tên có thể bị ghi đè hoặc chỉ giữ một entry nếu công cụ đóng gói không gộp service descriptors đúng cách.

Ví dụ ban đầu:

~~~text
upper.jar / META-INF/services/demo.spi.Formatter
  demo.plugins.Upper

lower.jar / META-INF/services/demo.spi.Formatter
  demo.plugins.Lower
~~~

Nếu một công cụ gộp JAR chỉ giữ file của upper.jar thì Lower có thể bị mất đăng ký, dù Lower.class vẫn tồn tại. Khi tạo fat JAR, resource cuối cùng phải chứa đủ các **tên provider khác nhau**:

~~~text
demo.plugins.Upper
demo.plugins.Lower
~~~

Sử dụng chức năng **merge META-INF/services** của công cụ đóng gói tương ứng; đừng chỉ kiểm tra rằng có class bytecode trong JAR. Loại bỏ bản ghi duplicate trong file sau merge là tùy chọn, nhưng mất bản ghi của một lớp khác là lỗi. Kiểm tra bản JAR cuối cùng bằng jar tf và đọc nội dung tài nguyên thực tế nếu cần.

Với dự án dùng Gradle Java plugin thông thường, đặt resource dưới src/main/resources để nó được đưa vào JAR. Khi dùng Shadow hoặc Maven Shade, cần kiểm tra transformer/merger dành cho service resources theo đúng phiên bản công cụ đang dùng.

## 7. Vì sao ServiceLoader có thể không thấy provider?

Câu lệnh ServiceLoader.load(Formatter.class) **chỉ tạo loader**; nó chưa bảo đảm mọi provider được nạp thành công. Cơ chế khám phá/khởi tạo lười có thể phát sinh ServiceConfigurationError khi code duyệt iterator, hasNext/next hoặc stream có thao tác buộc nạp provider.

Những nhóm lỗi đáng kiểm tra theo thứ tự:

- **Sai đường dẫn tài nguyên:** file có tên Formatter.txt, sai chữ hoa hoặc nằm dưới resources/META-INF/services bên trong JAR. Khi đó host có thể thấy 0 provider thay vì báo lỗi cụ thể.
- **Sai nội dung file:** dòng chứa import, new, dấu chấm phẩy, slash, tên class không hợp lệ, ký tự BOM đầu tệp, hoặc ký tự không phải encoding UTF-8 đúng.
- **Thiếu class khi runtime:** resource hợp lệ nhưng một provider được liệt kê không nằm trong classpath hoặc không thể được class loader truy cập.
- **Provider không phù hợp SPI:** class không assignable về Formatter thực sự mà host đang sử dụng, không phải class cụ thể, hoặc không có constructor public không tham số phù hợp với provider class trên classpath.
- **Lỗi trong constructor provider:** class được tìm thấy nhưng khởi tạo thất bại; kiểm tra nguyên nhân gốc trong lỗi.
- **Nhầm class loader:** cùng một tên interface được các class loader khác nhau định nghĩa thành hai kiểu khác nhau; tên chữ giống nhau chưa bảo đảm khả năng ép kiểu.
- **Mất file đăng ký khi đóng gói:** các class .class có trong fat JAR, nhưng service resource của một plugin đã bị ghi đè.

Thứ tự provider trả về trong trường hợp classpath gắn với thứ tự ClassLoader.getResources tìm các file cấu hình và thứ tự tên provider trong từng file. Không nên dùng thứ tự đó như quy tắc ưu tiên nghiệp vụ. Nếu cần chọn plugin ưu tiên, hãy xác định rõ id, priority, phiên bản hợp đồng và chính sách khi xung đột.

ServiceConfigurationError là một loại **Error**, vì vậy không nên bắt mọi lỗi rồi bỏ qua và tiếp tục với danh sách plugin thiếu mà không có chính sách. Trong hệ thống thực, host cần chọn giữa fail-fast, đưa plugin vào trạng thái lỗi hoặc cơ chế phục hồi có kiểm soát, kèm ghi log tên service, class, JAR và nguyên nhân.

## 8. Bài kiểm tra nhỏ để tự xác minh định dạng

Sau khi chạy ví dụ hoàn chỉnh ở mục 4, thử lần lượt:

1. Giữ nguyên hai lần khai báo Upper trong file thứ nhất và một lần ở file thứ hai. Kết quả vẫn có provider count=2.
2. Xóa **chỉ dòng trùng Upper** trong cả hai descriptor, giữ mỗi provider một dòng. Kết quả không đổi: lower=hello, upper=HELLO và provider count=2.
3. Thêm dòng # một đoạn chú thích UTF-8 vào một trong hai resource, đóng gói lại JAR. Kết quả không đổi.
4. Đổi tên META-INF/services/demo.spi.Formatter trong một JAR thành tên sai rồi đóng gói lại. Provider chỉ được đăng ký qua tài nguyên sai tên có thể biến mất; kiểm tra lại số provider và giải thích từ đường dẫn, không từ code implements.
5. Thay một tên provider bằng tên class không tồn tại. Khi thực sự duyệt ServiceLoader, xác minh lỗi cấu hình xuất hiện thay vì coi đó là dòng chú thích hay tự bỏ qua.
6. Đóng gói hai plugin thành một fat JAR, kiểm tra rằng **cả hai tên provider phân biệt** vẫn hiện diện trong một resource hợp nhất.

Các bài thử nên được chạy với classpath có kiểm soát và giữ bản gốc của tệp cấu hình để khôi phục sau mỗi lần thử. Khi thay đổi resource hoặc JAR, chạy lại ứng dụng/process mới để tránh đánh giá nhầm do class loader và cache vẫn đang hoạt động.

## 9. Ghi nhớ và tài liệu chuẩn

**Mỗi file có tên gì?** Tên nhị phân đầy đủ của *service* tại META-INF/services. **Mỗi dòng dữ liệu là gì?** Tên nhị phân đầy đủ của *provider class*.

**UTF-8 có bắt buộc không?** Có. Nên dùng UTF-8 không BOM, đặc biệt khi file được tạo từ Windows PowerShell 5.1 hoặc công cụ chuyển đổi encoding.

**Dấu # làm gì?** Nó biến phần còn lại của dòng thành chú thích. Dòng trắng, dấu cách/tab quanh tên và comment không tạo thêm provider.

**Trùng lặp được bỏ qua theo cái gì?** Theo **tên class provider**, kể cả khi lặp trong cùng file hoặc khác file. Điều đó không đảm bảo id nghiệp vụ duy nhất, không phải singleton trên JVM và không thay thế kiểm tra class hợp lệ.

**Muốn kiểm tra thực tế thì làm gì trước?** Xem nội dung JAR bằng jar tf, xác nhận tài nguyên nằm đúng classpath root, kiểm tra encoding và dòng khai báo, sau đó bắt buộc duyệt ServiceLoader để kích hoạt việc tìm và khởi tạo provider.

Tài liệu nền tảng: Java SE 17 API Specification, **java.util.ServiceLoader**, mục *Deploying service providers on the class path*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html

Một tệp đăng ký provider hợp lệ là một **hợp đồng về tài nguyên runtime**: đúng tên, đúng vị trí, đúng UTF-8, đúng cú pháp theo dòng. Hiểu rõ dấu # và phạm vi bỏ qua tên class trùng giúp tránh nhầm một dòng metadata với một provider instance hoặc với một plugin nghiệp vụ độc lập.
