# Tra cứu API và tùy chọn còn được hỗ trợ trên JDK đang dùng

## 1. Mục tiêu và nguyên tắc

Khi học các khả năng được giới thiệu từ Java 10, điều quan trọng trong dự án hiện tại là biết **API hoặc tùy chọn đó có dùng được với đúng JDK, runtime và nền tảng triển khai của mình hay không**. Không lấy phiên bản Java 10 làm mặc định cho môi trường chạy chỉ vì tên module học tập là “Java 10”. Ví dụ, suy luận kiểu biến cục bộ với `var` và `List.copyOf(...)` xuất hiện từ Java 10 và vẫn là kiến thức hữu ích trên các JDK hiện đại.

Sau bài này, bạn có thể:
- Xác định `java` và `javac` thực sự đang được chạy, kể cả khi máy cài nhiều JDK.
- Tra Javadoc đúng phiên bản để kiểm tra chữ ký, `Since`, trạng thái deprecated, preview và module chứa API.
- Xác minh tùy chọn dòng lệnh trên chính bộ công cụ đang sử dụng thay vì sao chép cờ từ tài liệu không cùng phiên bản.
- Kiểm tra khả năng biên dịch cho phiên bản Java đích bằng `javac --release`, sau đó chạy thử trên runtime đích.
- Dùng công cụ JDK để phát hiện phụ thuộc vào API lỗi thời hoặc API nội bộ, và biết giới hạn của từng công cụ.

**“Có trong JDK” khác với “phù hợp để sử dụng lâu dài”.** Một thành phần có thể tồn tại nhưng bị đánh dấu deprecated, nằm ở chế độ preview, không được xuất ra ngoài module, hoặc chỉ có trong một bản phân phối. Khả năng được nhà cung cấp tiếp tục cung cấp bản vá bảo mật cho bản JDK cũng là một vấn đề riêng, phải xem chính sách hỗ trợ của bản phân phối đó.

## 2. Xác định chính xác JDK đang dùng

Trước khi đọc tài liệu API hay thử một cờ JVM, hãy chạy:

~~~bash
java --version
javac --version
java --help
javac --help
~~~

- `java --version` cho biết phiên bản runtime/launcher đang được gọi. `javac --version` cho biết phiên bản compiler, có thể khác runtime.
- `java --help` và `javac --help` liệt kê các tùy chọn thông dụng của **chính phiên bản công cụ đó**. Đọc `--help-extra` khi cần tùy chọn bổ sung, nhưng đừng mặc định mọi cờ bổ sung đều ổn định hoặc dùng được ở mọi nhà cung cấp.
- Trên Windows PowerShell, dùng `Get-Command java,javac` hoặc `where.exe java` và `where.exe javac` để tìm file thực thi theo `PATH`. Trên Linux/macOS có thể dùng `command -v java` và `command -v javac`.
- Kiểm tra `JAVA_HOME` trong cấu hình build/IDE/CI. Việc shell chạy một JDK không chứng minh Gradle, Maven, IDE hay container đang dùng cùng JDK; đối chiếu cấu hình toolchain và log build ở đúng môi trường.

~~~powershell
Get-Command java,javac
$env:JAVA_HOME
~~~

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
~~~

Có thể dùng `java -XshowSettings:properties -version` khi cần kiểm tra các thuộc tính JVM như `java.home` và `java.version`. Đầu ra thay đổi tùy môi trường, nên đọc trực tiếp, không dựa vào chuỗi output chép sẵn.

Ghi lại ít nhất: nhà cung cấp/bản build JDK, major version, đường dẫn `java`/`javac` và Java version mà ứng dụng phải chạy ở production. Ví dụ: build trên JDK 27 nhưng deploy lên Java 17 thì **Java 17 mới là mức API và bytecode được phép sử dụng**.

## 3. Tra API bằng tài liệu đúng phiên bản

Ưu tiên **Java SE/JDK API Specification chính thức tương ứng với major version đang dùng**, đồng thời xem tài liệu của phiên bản runtime thấp nhất mà ứng dụng phải hỗ trợ. Ví dụ cổng tài liệu cho JDK 27: https://docs.oracle.com/en/java/javase/27/docs/api/ . Nếu môi trường của bạn dùng phiên bản khác, vào cổng tài liệu của phiên bản đó; đừng suy luận từ việc API xuất hiện trên trang của bản mới hơn.

Khi mở trang lớp/phương thức (ví dụ `java.util.List.copyOf`), kiểm tra tuần tự:

1. **Module và package:** API thuộc `java.base`/`java.util` hay module khác? Đây là Java SE API công khai hay JDK-specific API? Có cần khai báo `requires` trong `module-info.java` không? `java.base` được đọc mặc định bởi mọi module.
2. **Chữ ký phương thức và điều kiện sử dụng:** Kiểu tham số, kiểu trả về, overload, generic, ngoại lệ, khả năng nhận `null`, ghi chú về thread safety hoặc tính bất biến. Đọc mô tả từng method, không chỉ tên lớp.
3. **`Since`:** Xác định API được thêm từ bản nào. `Since: 10` của `List.copyOf(Collection)` cho biết API này đã có từ Java 10; không có nghĩa mọi phương thức khác của `List` đều có từ Java 10.
4. **Trạng thái vòng đời:** `Deprecated` là tín hiệu cần tìm cách thay thế; `forRemoval=true` có nghĩa API có thể bị xóa trong phiên bản tương lai, không có nghĩa nó đã bị xóa. Xem phần `Deprecated API` và khuyến nghị thay thế. Với preview/incubator/restricted API, đọc rõ điều kiện sử dụng của bản JDK hiện tại; tránh lựa chọn chúng cho code ổn định nếu không có quyết định kỹ thuật rõ ràng.
5. **Tính công khai và tính di động:** `jdk.internal.*` và các package không được export không phải lựa chọn API ổn định. Không suy ra một API được hỗ trợ chỉ vì IDE có thể tìm thấy tên class hoặc dùng reflection để truy cập được.

Ví dụ ở trang `List` của JDK 27, `List.copyOf(Collection)` có `Since: 10`; tài liệu mô tả danh sách trả về không thể thay đổi bằng các thao tác thêm/xóa phần tử, từ chối phần tử `null` và không thay đổi theo những chỉnh sửa sau đó của collection nguồn. Đây là ví dụ kiến thức bắt đầu ở Java 10 nhưng vẫn áp dụng hiện nay.

Liên kết tham khảo trực tiếp: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html .

### Không dùng riêng trang API của JDK mới nhất làm bằng chứng tương thích ngược

Nếu một phương thức có `Since: 21` trên Javadoc JDK 27, dự án phải hỗ trợ Java 17 thì phương thức đó chưa có trong API Java 17. Ngược lại, một API có `Since: 10` vẫn cần được kiểm tra trạng thái deprecated/removed ở **JDK đích**: thời điểm xuất hiện và tình trạng hiện tại là hai thông tin khác nhau.

Tài liệu API trả lời “API được đặc tả ra sao”; thử biên dịch với mức release phù hợp trả lời “mã của tôi có sử dụng API được phép cho target không”.

## 4. Dùng công cụ JDK để kiểm tra API ngay trên máy

~~~bash
java --list-modules
java --describe-module java.base
javap -public java.util.List
~~~

- `java --list-modules` liệt kê module có thể quan sát trên runtime đó; `java --describe-module java.base` hiển thị mô tả module, các package được export và thông tin phụ thuộc. Có module không đồng nghĩa mọi package trong module được truy cập công khai.
- `javap -public java.util.List` xem các thành viên public từ class/module mà công cụ hiện tại phân giải được. Rất hữu ích để tra nhanh chữ ký, nhưng không thay thế Javadoc về `Since`, deprecated, điều kiện biên hoặc tính tương thích với Java thấp hơn.
- Nếu API nằm trong dependency bên thứ ba, phải đọc **tài liệu và version của dependency đó**; API Specification của JDK không chứng minh một thư viện ngoài JDK có mặt hoặc được hỗ trợ.

Trong ứng dụng có module riêng, kiểm tra thêm `module-info.java`, `requires` và các package `exports`. Đừng dùng `--add-exports` hoặc `--add-opens` như giải pháp mặc định để dựa vào nội bộ JDK: các cờ ấy có mục đích tương thích/chẩn đoán trong hoàn cảnh cụ thể, không biến API nội bộ thành hợp đồng công khai dài hạn.

## 5. Xác minh tùy chọn của từng lệnh thay vì dùng cờ truyền miệng

Các nhóm công cụ khác nhau nhận các tùy chọn khác nhau:

| Muốn kiểm tra | Cách tra đầu tiên | Lưu ý |
| --- | --- | --- |
| Chạy ứng dụng, module, JVM | `java --help`; `java --help-extra`; Java launcher tool specification | Tùy chọn `-X`/`-XX` có thể phụ thuộc JVM và thay đổi theo release. |
| Biên dịch và mức tương thích Java | `javac --help`; `javac --help-extra` | `--release` chỉ nhận những mức được liệt kê trên compiler đang dùng. |
| Phân tích dependency | `jdeps --help` | Phân tích mã bytecode/JAR đã tạo; cần đủ classpath/module path khi phụ thuộc ngoài. |
| Rà soát Java SE API deprecated | `jdeprscan --help` | Công cụ kiểm tra API JDK được tham chiếu trong file đã biên dịch, không bao phủ API deprecated của thư viện ngoài. |
| Xem chữ ký class | `javap --help` | Kết quả phản ánh class mà bản JDK/classpath hiện tại tìm thấy. |

**Quy trình kiểm một cờ:** xác định lệnh nhận cờ → xem `--help` của lệnh trên máy/CI → đọc trang Tool Specifications đúng major version → đọc Release Notes nếu nâng JDK → chạy thử trên môi trường gần production trước khi đưa vào script.

Đừng nhầm `java` (launcher) với `javac` (compiler). Chẳng hạn, `--release` là tùy chọn của `javac`, không phải cờ để chuyển runtime của lệnh `java` thành một JDK khác.

Đối với cờ JVM chuyên sâu, sự hiện diện trong `--help-extra` không phải cam kết ổn định giữa HotSpot, OpenJ9 và các bản phân phối khác. Chỉ đưa cờ vào cấu hình vận hành sau khi đã xác nhận với tài liệu của đúng VM và kiểm tra trên phiên bản sẽ triển khai.

## 6. Kiểm tra mức Java đích bằng `javac --release`

Giả sử máy build dùng JDK hiện đại nhưng ứng dụng phải chạy trên Java 17. Có thể dùng:

~~~bash
javac --release 17 JdkLookupDemo.java
java JdkLookupDemo
~~~

Tùy chọn `--release 17` yêu cầu compiler biên dịch với quy tắc ngôn ngữ, bytecode và tập Java SE/JDK API khả dụng của bản Java 17 (theo dữ liệu mà compiler hỗ trợ). Điều này chặt chẽ hơn việc chỉ đặt `-source`/`-target` vì hai tùy chọn ấy không tự giới hạn đúng tập API của phiên bản cũ. Không kết hợp `--release` với `-source` hoặc `-target`.

Chỉ dùng số 17 ở ví dụ nếu `javac --help` của máy xác nhận hỗ trợ giá trị đó và đây là Java mục tiêu của dự án. Mức release mà một bản compiler hỗ trợ là hữu hạn và thay đổi theo bản JDK; không giả định compiler hiện tại có thể nhắm tới mọi bản Java trong lịch sử.

**Quan trọng:** `--release` giới hạn biên dịch; nó **không** tự tạo hoặc chạy một JVM Java 17. Vẫn cần chạy integration/smoke test trên đúng runtime và dependency thực tế. Tập API tồn tại trong bản JDK mà bạn cài và chu kỳ nhận bản vá bảo mật của nhà cung cấp là hai kiểm tra độc lập.

## 7. Ví dụ chạy được: xác nhận hai khả năng xuất hiện từ Java 10

Ví dụ sau dùng `var` (suy luận kiểu cho biến cục bộ) và `List.copyOf` (tạo danh sách không thể sửa) — đều sử dụng được trên JDK 17 trở lên. Lưu tệp đúng tên **`JdkLookupDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class JdkLookupDemo {
    public static void main(String[] args) {
        var source = new ArrayList<String>();
        source.add("Java");
        source.add("JDK");

        List<String> snapshot = List.copyOf(source);
        source.add("Tooling");

        System.out.println(snapshot);
        System.out.println(source);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 JdkLookupDemo.java
java JdkLookupDemo
~~~

**Stdout chính xác:**

~~~text
[Java, JDK]
[Java, JDK, Tooling]
~~~

Diễn giải:
- `var source` vẫn có kiểu tĩnh là `ArrayList<String>` do compiler suy luận từ biểu thức khởi tạo. `var` không có nghĩa là kiểu động và không áp dụng tùy tiện cho trường dữ liệu hay kiểu trả về của phương thức.
- `List.copyOf(source)` tạo danh sách không thể sửa có các phần tử tại thời điểm gọi. Thêm `"Tooling"` vào danh sách nguồn sau đó không làm thay đổi `snapshot`.
- Thao tác `snapshot.add("Khác")` sẽ ném `UnsupportedOperationException`; `List.copyOf` cũng không chấp nhận phần tử `null`. Không cần thực thi các thao tác gây lỗi này để chứng minh output.
- Khi kiểm tra bằng Javadoc, đối chiếu `Since: 10` của `List.copyOf` và quy tắc `var` với target project. Sau đó biên dịch với `--release` đúng target và chạy bằng JVM đích.

Ví dụ chỉ cần Java chuẩn, không sử dụng dependency ngoài. Nếu dùng JDK 21, 25 hoặc 27 để biên dịch với `--release 17`, chạy bằng Java 17 trở lên theo điều kiện dự án; nếu runtime đích thấp hơn Java 17, hãy chọn release tương ứng và kiểm tra lại toàn bộ API.

## 8. Rà soát API deprecated và phụ thuộc vào JDK internals

Trong mã nguồn đang phát triển, compiler giúp phát hiện gọi API deprecated:

~~~bash
javac -Xlint:deprecation JdkLookupDemo.java
javac -Xlint:removal JdkLookupDemo.java
~~~

Mẫu `JdkLookupDemo` không sử dụng API deprecated, nên không kỳ vọng cảnh báo deprecation từ hai lệnh trên. Với ứng dụng thực có phụ thuộc, hãy biên dịch mọi module liên quan và xem cảnh báo theo build log. `-Xlint:removal` đặc biệt hữu ích để nhìn các API có nguy cơ bị loại bỏ.

Đối với bytecode hoặc JAR đã build (ví dụ dự án có tệp `build/libs/app.jar`), dùng:

~~~bash
jdeprscan --for-removal build/libs/app.jar
jdeps --jdk-internals build/libs/app.jar
~~~

- `jdeprscan` rà việc dùng các phần tử Java SE API deprecated; `--for-removal` thu hẹp về các phần tử bị đánh dấu có khả năng xóa. Nó không kiểm tra mọi dependency bên thứ ba và có thể cần classpath để phân tích đủ.
- `jdeps --jdk-internals` phát hiện phụ thuộc vào API nội bộ của JDK. Kết quả là tín hiệu cần chuyển sang API công khai phù hợp; không mặc định chữa bằng cách mở rộng quyền truy cập module.
- Hai công cụ phân tích bytecode nên chạy sau khi có bản build. Nếu thiếu class/dependency, sửa đường dẫn classpath/module path rồi mới kết luận kết quả quét.

Không coi việc `jdeprscan` không báo lỗi là bảo đảm tất cả API đều an toàn lâu dài. Vẫn cần xem Javadoc, Release Notes và trạng thái hỗ trợ của nhà cung cấp.

## 9. Cách xử lý khi kết quả kiểm tra mâu thuẫn

| Triệu chứng | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| IDE gợi ý method nhưng `javac --release 17` không biên dịch được | Method được bổ sung sau Java 17, hoặc dependency không đúng | Xem `Since` của method, phiên bản dependency, import và `--release`. |
| Biên dịch thành công trên máy dev nhưng production báo `UnsupportedClassVersionError` | Bytecode target cao hơn Java runtime đang chạy | Đối chiếu `javac --release`/toolchain và `java --version` của production. |
| Lúc chạy gặp `NoSuchMethodError` | Runtime tải bản thư viện hoặc API khác bản khi biên dịch | Kiểm tra classpath/module path, dependency thực tế, runtime version. |
| Thấy tên class trong JDK nhưng không import/truy cập được | Package không được export hoặc API nội bộ | Xem module/package trên Javadoc, `java --describe-module` và chọn API công khai. |
| Script JVM báo tùy chọn không nhận diện được | Cờ không có ở release/VM thực tế hoặc cú pháp thay đổi | Kiểm tra executable, `java --help-extra`, tool docs và release notes của phiên bản đang chạy. |
| API vẫn compile nhưng có deprecation warning | API còn hiện diện nhưng không còn là lựa chọn khuyến nghị | Đọc lý do deprecated, `forRemoval` và API thay thế; lên kế hoạch chuyển đổi. |

Không dùng sự thành công của một môi trường để suy ra cho mọi môi trường. Đặc biệt, container image, CI runner và máy production thường có phiên bản JDK hoặc dependency khác nhau.

## 10. Checklist áp dụng cho dự án thật

1. **Xác nhận môi trường:** `java --version`, `javac --version`, đường dẫn hai executable, vendor/VM, JDK của build tool và runtime của production.
2. **Chọn mức thấp nhất cần hỗ trợ:** quyết định target Java theo yêu cầu triển khai; xem `javac --help` xác nhận `--release` tương ứng có hiệu lực.
3. **Tra API đúng nơi:** mở Java SE/JDK API Specification của version đích; kiểm tra module, visibility, chữ ký, `Since`, exception, deprecation, preview và các hành vi liên quan.
4. **Kiểm tra cờ đúng công cụ:** chạy `--help` và trang Tool Specifications trên đúng JDK/VM, đặc biệt nếu cờ lấy từ bài viết cũ hoặc cấu hình dự án khác.
5. **Biên dịch và chạy kiểm chứng:** dùng `--release` khi hỗ trợ target thấp hơn; chạy test bằng runtime đích; nếu có JAR ứng dụng, rà `jdeprscan` và `jdeps` khi phù hợp.
6. **Kiểm tra thay đổi khi nâng cấp:** đọc Release Notes, phần API/option removed hoặc deprecated, kiểm thử CI và xác định trạng thái hỗ trợ bảo mật từ nhà cung cấp JDK đang triển khai.

### Tài liệu chính thức nên lưu

- [JDK 27 — API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/) và [java.util.List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): ví dụ của **cấu trúc tài liệu versioned**; hãy chọn đúng version mà dự án chạy.
- [Java SE/JDK 27 Specifications](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html): điểm vào Java Language Specification, JVM Specification và JDK Tool Specifications.
- [JDK 27 Documentation](https://docs.oracle.com/en/java/javase/27/): công cụ, thư viện, hướng dẫn vận hành và migration.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): nơi xem thay đổi, API/tùy chọn bị loại bỏ hoặc deprecated ở release này.
- [Tài liệu `javac` JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): mô tả chính thức của `--release` và hạn chế kết hợp với `-source`/`-target`; khi dùng JDK khác, tra cùng mục ở tài liệu release đó.

**Tiêu chí hoàn thành:** Bạn chỉ kết luận một API hoặc tùy chọn “dùng được cho dự án” sau khi biết **bản JDK đang chạy**, **target runtime**, **trạng thái chính thức của API/cờ**, và có **kết quả biên dịch/chạy hoặc kiểm chứng cấu hình tương ứng**.