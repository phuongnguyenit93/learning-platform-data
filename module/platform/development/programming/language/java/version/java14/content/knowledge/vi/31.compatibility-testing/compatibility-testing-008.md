# Tra cứu API bị deprecated hoặc loại bỏ trong JDK đích

## 1. Mục tiêu học tập

Khi nâng cấp một ứng dụng từ Java 17 lên Java 21, 24, 25 hoặc một JDK mới hơn, **mã còn biên dịch** chưa chắc có nghĩa **mọi API còn được khuyến nghị**. Ngược lại, một API được đánh dấu `@Deprecated` chưa chắc đã bị xóa khỏi runtime hiện tại. Muốn kết luận chính xác cần đặt câu hỏi đối với **phiên bản JDK đích**, không chỉ phiên bản JDK đang chạy ở máy phát triển.

Bài này hướng dẫn quy trình còn áp dụng cho Java hiện đại:

1. Phân biệt **deprecated**, **deprecated for removal** và **removed**.
2. Tra cứu Javadoc **Deprecated API** và **Removed APIs** theo phiên bản.
3. Dùng `javac -Xlint:deprecation,removal` để kiểm tra **source**.
4. Dùng `jdeprscan` để quét các lời gọi Java SE API deprecated từ **class/JAR đã biên dịch**.
5. Dùng `javac --release N` hoặc `javac` của JDK đích để phát hiện **API không còn tồn tại**; `jdeprscan` không thay thế bước này.
6. Dùng `jdeps` và kiểm thử runtime đích để xác minh dependency, module, reflection và compatibility.
7. Xử lý warning có ưu tiên, viết mã thay thế **không dùng API legacy**, giữ nguyên hành vi nghiệp vụ.
8. Tích hợp các kiểm tra vào CI/CD mà không vô tình thay đổi minimum runtime của bản phát hành.

**Nguyên tắc:** tài liệu JDK 17 mô tả trạng thái tại Java 17; tài liệu JDK 25 mô tả trạng thái tại Java 25. Không lấy trạng thái “deprecated từ năm nào” làm bằng chứng API vẫn còn hoặc đã bị xóa ở một JDK khác.

## 2. Ba trạng thái hoàn toàn khác nhau

| Trạng thái | Nghĩa đối với source/runtime | Kiểm tra bằng | Quyết định kỹ thuật |
| --- | --- | --- | --- |
| **Deprecated thông thường** | API còn có thể tồn tại, nhưng không được khuyến nghị tiếp tục dùng | Javadoc, `-Xlint:deprecation`, `jdeprscan` | Lên kế hoạch chuyển sang API được đề xuất |
| **Deprecated for removal** | API bị đánh dấu với **ý định loại bỏ** trong một release tương lai | `@Deprecated(forRemoval=true)`, `-Xlint:removal`, `jdeprscan --for-removal` | Ưu tiên loại bỏ phụ thuộc sớm; không chờ tới khi build hỏng |
| **Removed** | API **không còn được cung cấp** ở JDK đích; gọi trực tiếp có thể compile fail hoặc runtime link fail | Removed APIs guide, Javadoc đích, compile/test bằng JDK đích | Phải sửa code/dependency hoặc thay đổi JDK mục tiêu |

**Cần nhớ:**

- `@Deprecated` **không xóa** một class/method/constructor.
- `forRemoval=true` là **ý định**, **không phải lịch xóa chắc chắn trong JDK kế tiếp**.
- API bị xóa ở JDK đích sẽ không còn là một thành viên có thể biên dịch bằng API hiện hành; vì vậy **đừng coi việc không xuất hiện trong danh sách deprecated là an toàn**.
- Từ góc độ compatibility, cần phân biệt lỗi do **API JDK** với lỗi do **thư viện bên thứ ba**, JDK internal API hoặc thay đổi cấu hình runtime.
- Những API cũ trong bài chỉ xuất hiện trong **mẫu mã kiểm toán âm tính** để học cách phát hiện và di trú; **không phải API được khuyến nghị cho ứng dụng mới**.

### Một ví dụ theo release thực tế

- `java.util.Date.getYear()` là API deprecated thông thường; code mới nên dùng `java.time` và lựa chọn múi giờ có chủ đích.
- Constructor `new Integer(int)` là deprecated **for removal** trên các JDK đã kiểm thử; code mới dùng `Integer.valueOf(int)` hoặc autoboxing có chủ đích.
- `java.lang.Thread.resume()` đã bị **loại bỏ từ JDK 23**, nên không thể dùng trong code nhắm JDK 24; không có bản thay thế “đổi tên là xong” — phải thiết kế lại giao thức đồng bộ/điều khiển luồng.

Các trạng thái kể trên đã được đối chiếu với JDK 24 và tài liệu Removed APIs của Oracle; khi dự án nhắm JDK khác, vẫn phải tra **đúng tài liệu của phiên bản đích**.

## 3. Hiểu chính xác chú thích @Deprecated

Kể từ JDK 9, annotation `java.lang.Deprecated` có hai thành phần quan trọng:

~~~java
@Deprecated(since = "17", forRemoval = true)
~~~

Đây là **ví dụ cú pháp annotation**, không phải lời khuyên đánh dấu API tùy ý là deprecated.

- `since`: **release lần đầu API được đánh dấu deprecated**, **không phải** release API được thêm vào và cũng **không phải ngày chắc chắn bị xóa**.
- `forRemoval=false`: tại thời điểm đánh dấu, API không được khuyến nghị nhưng **chưa có ý định cụ thể loại bỏ**.
- `forRemoval=true`: API **được dự kiến có thể loại bỏ** trong một bản Java sau; người dùng cần tránh phụ thuộc vào nó.
- Không có quy tắc rằng một API `forRemoval=true` chắc chắn bị xóa ở bản JDK ngay kế tiếp.
- `@Deprecated` có runtime retention, nhưng công cụ phân tích source/binary và **Javadoc phiên bản đích** thường thực tế hơn việc tự dùng reflection để duyệt từng API.

Javadoc có cả thẻ:

~~~java
/**
 * @deprecated Lý do và đường di trú sang API thay thế.
 */
@Deprecated(since = "17", forRemoval = false)
public void oldMethod() {
    // Mảnh minh họa của API do ứng dụng tự định nghĩa.
}
~~~

**Phân biệt:** `@Deprecated` là annotation dùng bởi compiler/công cụ; `@deprecated` viết trong Javadoc giải thích **vì sao** và **thay bằng gì**. Hai cách ghi bổ trợ nhau.

### Không phải deprecated nào cũng có một phép thay tên tương đương

Một API có thể bị deprecated vì lỗi bảo mật, hiệu năng, tính không rõ ràng, thiết kế kém hoặc cách vận hành đã khác. Đổi phương thức cũ sang phương thức mới **có thể thay đổi semantics**: múi giờ, giá trị trả về, cách xử lý null, thứ tự, exceptions, quyền truy cập hoặc concurrency.

Do đó ngoài việc tìm “replacement”, hãy kiểm tra **hợp đồng mới**, các tình huống biên và kiểm thử hồi quy.

## 4. Bước đầu: xác định đúng phiên bản JDK đang phân tích

Trước khi đọc warning hoặc chạy scanner:

~~~bash
java -version
javac -version
jdeprscan --version
jdeprscan --help
~~~

Các lệnh có thể đến từ **những JDK khác nhau** nếu PATH được cấu hình không nhất quán. Trên Windows PowerShell:

~~~powershell
(Get-Command java).Source
(Get-Command javac).Source
(Get-Command jdeprscan).Source
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
command -v jdeprscan
~~~

Nếu cần scan **API của Java 25**, hãy dùng `jdeprscan` đủ mới và kiểm tra `--help` của nó có hỗ trợ `--release 25`. Một `jdeprscan` JDK 24 không thể tự nhiên phân tích deprecation metadata **của Java 25** chỉ bằng việc tự thêm option không được hỗ trợ.

Nếu dự án dùng Maven, Gradle hay CI toolchains, cần xác định JDK của **job build và job test thật**, không dựa vào JDK được hiển thị ở IDE của một developer.

## 5. Tra cứu Javadoc Deprecated API theo phiên bản

Oracle cung cấp **Deprecated API list** theo từng major JDK:

- JDK 17: https://docs.oracle.com/en/java/javase/17/docs/api/deprecated-list.html
- JDK 21: https://docs.oracle.com/en/java/javase/21/docs/api/deprecated-list.html
- JDK 24: https://docs.oracle.com/en/java/javase/24/docs/api/deprecated-list.html
- JDK 25: https://docs.oracle.com/en/java/javase/25/docs/api/deprecated-list.html
- JDK 26: https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html

Trang thường tách nhóm **Terminally Deprecated Elements** (đánh dấu for removal) và những deprecated elements khác. Với từng entry, hãy click vào API cụ thể để xem:

1. API thuộc module/package/class nào.
2. Annotation có `since` và `forRemoval` hay không.
3. Lý do deprecated trong Javadoc.
4. API được khuyến nghị thay thế — nếu có.
5. Khác biệt về hành vi hoặc ràng buộc.
6. Tên method/constructor cùng kiểu tham số; tránh nhầm các overload.

**So sánh ít nhất hai bản:** baseline hiện có và JDK dự kiến nâng cấp. Ví dụ nếu chuyển Java 17 → 25, hãy đọc cả trang deprecated-list của 17 **và** 25. Một API có thể được đánh dấu deprecated sau 17 nên code build trên Java 17 chưa từng được cảnh báo.

**Không suy luận “API không thấy trong deprecated-list của 25 = API còn tốt”.** Nó có thể đã **bị xóa**, bị chuyển sang trạng thái khác, là JDK-specific/non-Java SE hoặc chưa được scanner hỗ trợ. Khi không tìm thấy, tra **API documentation của class**, danh sách **Removed APIs**, migration/release notes và kiểm tra bằng compiler của JDK đích.

## 6. Tra danh sách Removed APIs và migration notes

Oracle Migration Guide có trang **Removed APIs**:

- JDK 25: https://docs.oracle.com/en/java/javase/25/migrate/removed-apis.html
- JDK 26: https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html

Đây là nơi kiểm tra **API Java SE nào thực sự đã bị xóa** theo release. Chẳng hạn tài liệu JDK 25 ghi:

- JDK 21: lớp `java.lang.Compiler` bị loại bỏ.
- JDK 22: phương thức `Thread.countStackFrames()` bị loại bỏ.
- JDK 23: các phương thức `Thread.resume()` và `Thread.suspend()` bị loại bỏ, cùng các API thread group tương ứng.
- JDK 24: một số field cũ, như `javax.naming.Context.APPLET`, bị loại bỏ.

Những tên này chỉ giúp nhận diện **tính không tương thích khi nâng JDK**. Không dùng các API đã bị loại bỏ để viết code nghiệp vụ mới.

**Lưu ý:** Removed APIs list của một bản JDK thường tập trung vào những API Java SE đã bị loại bỏ trong các release được tài liệu bao phủ. Đối với một vendor JDK cụ thể, cần đọc thêm **release notes của vendor, JEP liên quan, thay đổi tùy chọn JVM, module và native behavior**. Những thay đổi đó có thể gây lỗi runtime dù API Java SE chưa bị đánh dấu deprecated.

### Vì sao xem cả Deprecated và Removed?

- Deprecated list trả lời: “**API nào đang bị cảnh báo** theo phiên bản này?”
- Removed APIs trả lời: “**API Java SE nào không còn** ở phiên bản này so với trước?”
- `javac --release <target>` hoặc compiler JDK đích trả lời: “**Source của tôi còn được compiler/type checker chấp nhận với API của target không?**”
- Runtime tests trả lời: “**Artifact thực sự chạy đúng trên runtime mục tiêu không?**”

Không có một nguồn nào trả lời trọn vẹn tất cả.

## 7. Bật cảnh báo khi biên dịch source

Dùng hai nhóm lint riêng:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
  -encoding UTF-8 -d out AuditOnly.java
~~~

Ý nghĩa:

- `--release 17`: target ngôn ngữ, JDK API và class format Java 17.
- `-Xlint:deprecation`: thông báo các lời gọi API **deprecated thông thường**.
- `-Xlint:removal`: thông báo các API bị **đánh dấu for removal**.
- `-encoding UTF-8`: đọc source file theo UTF-8.
- `-d out`: đặt class files trong folder output.

Trên các JDK hiện đại, warning nhóm **removal** thường đã được bật mặc định, còn `-Xlint:deprecation` giúp thấy vị trí cụ thể thay vì chỉ thấy thông báo tổng hợp.

### Chặn warning bằng -Werror khi cần

~~~bash
javac --release 17 -Xlint:deprecation,removal -Werror \
  -encoding UTF-8 -d out AuditOnly.java
~~~

`-Werror` làm cho **bất kỳ warning được phát ra** trở thành lỗi build, không chỉ warning deprecated. Hãy dùng với mã đã làm sạch và chính sách CI cụ thể.

Cách triển khai thường hợp lý:

1. Bật lint và thu thập danh sách cảnh báo trước.
2. Phân loại lỗi thực, thứ tự ưu tiên và thư viện bên ngoài.
3. Di trú rồi kiểm thử hồi quy.
4. Khi repository đã sạch, bật `-Werror` ở phạm vi dự án phù hợp để tránh tái phạm.

**Không dập hết warning bằng `@SuppressWarnings("deprecation")` hoặc `@SuppressWarnings("removal")`** nếu chưa giải thích lý do và rủi ro. Suppression chỉ làm cảnh báo biến mất, **không khôi phục API đã bị xóa**.

## 8. Ví dụ kiểm toán âm tính đã kiểm thử trên JDK 24

Phần này **cố tình chứa hai lời gọi không nên dùng trong code mới** để chứng minh công cụ phát hiện được các mức deprecated khác nhau. Không tái sử dụng class này trong hệ thống sản xuất.

Tạo file **`AuditOnly.java`**:

~~~java
import java.util.Date;

public class AuditOnly {
    static int oldYear(Date date) {
        return date.getYear();
    }

    static Integer obsoleteBoxing(int value) {
        return new Integer(value);
    }
}
~~~

Biên dịch để lấy warning:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
  -encoding UTF-8 -d out AuditOnly.java
~~~

Trên Azul OpenJDK 24.0.2, lệnh **compile thành công** nhưng phát hai warning:

~~~text
warning: [deprecation] getYear() in Date has been deprecated
warning: [removal] Integer(int) in Integer has been deprecated and marked for removal
2 warnings
~~~

Đây là **ba dòng cốt lõi của output thật**. Compiler còn in đường dẫn, vị trí và trích source; các chi tiết phụ có thể khác giữa máy/JDK.

Tại sao compile vẫn PASS? `@Deprecated` **không cấm** một API còn tồn tại. Mặc định warning không đồng nghĩa error. Nếu thêm `-Werror`, build sẽ không còn thành công khi warning vẫn có mặt.

### Đọc đúng kết quả

- `Date.getYear()`: deprecated thông thường; không tự suy rằng nó sẽ bị xóa vào release tới.
- `Integer(int)`: deprecated for removal; nên thay bằng `Integer.valueOf(value)` hoặc autoboxing.
- Tìm **lời gọi thực tế trong source**, không chỉ loại class. Ví dụ `java.util.Date` chưa bị xóa, nhưng nhiều method bên trong class đã deprecated.
- Nếu source là code của dependency bên thứ ba, đừng sửa trực tiếp trong thư mục build cache; nâng version hoặc liên hệ maintainer.

**Tách biệt bản audit khỏi code hiện đại:** ở mục 12 có chương trình mới không sử dụng API deprecated; mục 8 chỉ tồn tại để học cách đọc lint/scanner.

## 9. Quét class/JAR bằng jdeprscan

`jdeprscan` là công cụ phân tích **bytecode**, khác với `javac` phân tích source. Nó có ích khi:

- Bạn có thư viện JAR đã biên dịch nhưng không sở hữu source.
- Source code đã ở nhiều module, còn artifact được đóng gói khác.
- Cần xem một library đang dùng **Java SE APIs deprecated**.
- Muốn phân biệt lời gọi thường và lời gọi được đánh dấu **for removal**.

### 9.1. Cú pháp cơ bản

~~~bash
jdeprscan --version
jdeprscan --help
jdeprscan --release 17 out
~~~

Trong đó `out` là thư mục class được tạo từ ví dụ `AuditOnly` ở mục 8. Kết quả đã kiểm thử trên `jdeprscan 24.0.2` với deprecation catalog Java 17:

~~~text
class AuditOnly uses deprecated method java/util/Date::getYear()I
class AuditOnly uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

Đây là **hai dòng phát hiện**; công cụ còn in dòng tên thư mục đang quét, phụ thuộc đường dẫn trên máy.

Ký hiệu `java/util/Date::getYear()I` sử dụng JVM internal name và method descriptor. `I` ở đây là kiểu trả về `int`; `<init>` là constructor. Đừng nhầm output của scanner là Java source.

### 9.2. Chỉ quét API for removal

~~~bash
jdeprscan --release 17 --for-removal out
~~~

Đầu ra đã kiểm thử chỉ có:

~~~text
class AuditOnly uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

`--for-removal` **lọc** kết quả để ưu tiên các API có `forRemoval=true`. Nó không phải option “kiểm tra tất cả API đã bị xóa”!

### 9.3. Chọn deprecation catalog của JDK đích

~~~bash
jdeprscan --release 24 out
jdeprscan --release 24 --for-removal out
~~~

Những lệnh này sử dụng danh sách trạng thái deprecated **cho Java 24**, với điều kiện scanner JDK đang chạy hỗ trợ `--release 24`. Khi nâng lên JDK 25/26, dùng scanner tương ứng đã cài và đọc `jdeprscan --help` để chọn catalog target được hỗ trợ.

**Cực kỳ quan trọng:** `--release 17` trong `jdeprscan` chỉ chọn **bộ danh sách deprecated API tại Java 17**. Nó **không giống** `javac --release 17`, vốn cấu hình ngôn ngữ/API/bytecode cho quá trình biên dịch.

### 9.4. Scan JAR đã đóng gói

~~~bash
jdeprscan --release 24 application.jar
jdeprscan --release 24 --for-removal application.jar
~~~

Đây là **lệnh minh họa**, cần có `application.jar` thực. Nếu ứng dụng phụ thuộc các JAR khác:

~~~bash
jdeprscan --release 24 --class-path "lib/*" application.jar
~~~

Tùy shell, hãy truyền class path sao cho JDK/tool thực sự resolve được các classes; cú pháp wildcard và quoting phải được kiểm tra trong môi trường build. Với nhiều đường dẫn, class path separator là `;` trên Windows và `:` trên Linux/macOS.

Nếu scanner báo:

~~~text
error: cannot find class ...
~~~

thì **không được coi bản scan đã bao phủ đầy đủ**. Hãy bổ sung các dependencies cần thiết qua `--class-path` hoặc cách scan tương ứng.

### 9.5. Xem danh sách mà chưa cần có artifact

~~~bash
jdeprscan --release 24 --list
jdeprscan --release 24 --for-removal --list
~~~

`--list` chỉ in danh sách API deprecated trong catalog, **không quét mã của dự án**. Khi dùng `--list`, không truyền thêm tên folder/JAR/class cần scan.

## 10. Những giới hạn quan trọng của jdeprscan

### 10.1. Không tự báo mọi API đã bị xóa

Công cụ chủ yếu tìm **tham chiếu tới API Java SE đang được đánh dấu deprecated trong catalog được chọn**. Khi một API đã bị xóa khỏi JDK đích, **không có gì bảo đảm scanner sẽ báo tham chiếu đó**. Một lần scan không có output **không phải** giấy chứng nhận code dùng được trên JDK đích.

Trong thử nghiệm JDK 24, class dùng `Thread.resume()` biên dịch với API Java 17 (kèm warning). Tuy nhiên `jdeprscan --release 17` và `jdeprscan --release 24` trên artifact đã biên dịch **không in phát hiện cho trường hợp này**. Đây là quan sát của môi trường test, cho thấy cần **bước compile/test trên JDK đích** bên cạnh scanner.

### 10.2. Không bao quát tất cả thư viện ngoài

Theo tài liệu `jdeprscan` hiện hành, phạm vi deprecated API do scanner nhận diện là **Java SE**, **không phải mọi API deprecated của thư viện bên thứ ba**. Muốn kiểm tra deprecation của thư viện bên ngoài:

- Bật `javac -Xlint:deprecation,removal` khi compile source có lời gọi tới thư viện đó.
- Xem Javadoc/API docs, migration guide và release notes của **thư viện và đúng version**.
- Kiểm tra static analysis hỗ trợ dependency tương ứng, nếu có.
- Chạy integration tests trên thư viện/JDK sẽ được triển khai.

**Không nhầm JDK-specific API với Java SE**; khi dùng `com.sun.*` được export công khai, phải xem tài liệu module/vendor phù hợp. Khi dùng nội bộ `sun.*`, `jdeps --jdk-internals` là một bước riêng để điều tra.

### 10.3. Không phát hiện hết lời gọi động

Reflection, `Class.forName`, method handles, `ServiceLoader`, JNI, generated bytecode, dynamic plugins hoặc cấu hình chọn class theo tên có thể làm API chỉ được tham chiếu **lúc chạy**. Scanner tĩnh không chứng minh mọi nhánh đều tương thích.

### 10.4. Trạng thái phụ thuộc bản JDK dùng để quét

Một JDK scanner chỉ biết những releases được hỗ trợ qua `jdeprscan --help`. Đừng chạy bản JDK cũ hơn target, tự nhập `--release 26` rồi giả định chương trình hiểu trạng thái deprecation của JDK 26.

### 10.5. Không tự biến warning thành build failure

`jdeprscan` có thể in các phát hiện nhưng kết thúc với exit code **0**. Trong thử nghiệm có hai API deprecated mà `scan-exit=0`. Vì vậy CI cần **chính sách xử lý báo cáo**, không được coi exit code 0 là “không có deprecated API”.

## 11. Phát hiện API đã removed bằng compiler JDK đích

Đây là bước **bắt buộc bổ sung** khi nâng target runtime: kiểm tra API **còn tồn tại hay không** trong JDK đích.

Oracle Removed APIs guide xác nhận `Thread.resume()` đã bị loại bỏ trong Java 23. Không nên gọi phương thức này trong ứng dụng; mẫu dưới đây **chỉ để kiểm tra biên dịch**, tuyệt đối không chạy.

Tạo file **`RemovedApiProbe.java`**:

~~~java
public class RemovedApiProbe {
    static void legacy(Thread thread) {
        thread.resume();
    }
}
~~~

### 11.1. Biên dịch với API baseline Java 17

Trên `javac` JDK 24:

~~~bash
javac --release 17 -Xlint:removal \
  -encoding UTF-8 -d out17 RemovedApiProbe.java
~~~

Kết quả kiểm thử:

~~~text
warning: [removal] resume() in Thread has been deprecated and marked for removal
1 warning
~~~

**Cảnh báo này không có nghĩa API vẫn tồn tại trên JDK 24**. Nó chỉ nói rằng `javac --release 17` đang dùng **API Java 17**, thời điểm đó `resume()` còn hiện diện nhưng deprecated for removal.

### 11.2. Biên dịch kiểm tra riêng cho JDK 24

~~~bash
javac --release 24 -encoding UTF-8 -d out24 RemovedApiProbe.java
~~~

Kết quả đã kiểm thử trên JDK 24:

~~~text
error: cannot find symbol
  symbol:   method resume()
  location: variable thread of type Thread
1 error
~~~

Tên biến trong dòng `location` và đường dẫn file phụ thuộc cách viết source. **Điểm chính:** `Thread.resume()` **không còn trong Java 24 API** nên source không biên dịch khi nhắm Java 24.

### 11.3. Giữ nguyên production baseline khi làm migration check

Nếu sản phẩm **vẫn cần hỗ trợ Java 17**, không vô tình thay bản phát hành bằng build `--release 24` chỉ để scan. Nên tách:

- **Build phát hành:** `--release 17`, tạo class major 61.
- **Migration-check build riêng:** biên dịch/test với JDK 24 API, tìm những lời gọi không còn hợp lệ.
- **Runtime test:** chạy **artifact major 61 của production** bằng Java 17 và Java 24 để bắt lỗi liên kết/tương thích.

Muốn đổi minimum runtime từ 17 lên 24 thì đó là **thay đổi hợp đồng sản phẩm**, cần cập nhật docs, dependencies và test matrix. Không dùng một compiler flag như sự thay thế cho quyết định này.

## 12. Mã hiện đại thay thế: chương trình Java 17+ chạy độc lập

Ví dụ trước chỉ minh họa code **cần được di trú**. Chương trình dưới đây dùng API hiện hành đã ổn định, không gọi API deprecated.

Tạo **`ModernReplacement.java`**:

~~~java
import java.time.LocalDate;
import java.util.TimeZone;

public class ModernReplacement {
    public static void main(String[] args) {
        System.out.println("year=" +
                LocalDate.of(2025, 11, 7).getYear());
        System.out.println("boxed=" +
                Integer.valueOf(42));
        System.out.println("zone=" +
                TimeZone.getTimeZone("UTC").getID());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d modern ModernReplacement.java
java -cp modern ModernReplacement
~~~

**Stdout đã kiểm thử trên OpenJDK 24:**

~~~text
year=2025
boxed=42
zone=UTC
~~~

Phân tích:

- `LocalDate.of(...).getYear()` trả năm thực của một ngày cụ thể. `LocalDate` từ Java Time API, được khuyến nghị cho code ngày tháng mới.
- `Integer.valueOf(42)` có thể tận dụng caching và không cần constructor `new Integer(int)` deprecated.
- `TimeZone.getTimeZone("UTC")` trong ví dụ chỉ minh họa múi giờ cố định, không phải hướng dẫn thay mọi `ZoneId` bằng `TimeZone`.

**Quan trọng khi chuyển Date.getYear():** phương thức cũ trả **`năm - 1900` theo local timezone**, còn `LocalDate.getYear()` trả **năm dương lịch đầy đủ**. Muốn chuyển từ một `Date` chứa instant sang năm theo múi giờ do ứng dụng lựa chọn, dùng:

~~~java
int year = date.toInstant()
        .atZone(zoneId)
        .getYear();
~~~

Đây là **mảnh code tích hợp**: `date` kiểu `java.util.Date`, `zoneId` kiểu `java.time.ZoneId`. Múi giờ phải được chọn theo hợp đồng, không mặc định tương đương mọi hành vi legacy. Nếu hệ thống cũ lưu năm dưới dạng offset 1900, cần migration dữ liệu riêng.

**Không cố đưa ra một replacement trực tiếp cho Thread.resume().** Điều khiển luồng bằng suspend/resume nguy hiểm về đồng bộ hóa; cần thiết kế lại với `interrupt`, `ExecutorService`, `Lock`/`Condition` hoặc hàng đợi sự kiện theo bài toán cụ thể. Không phải trường hợp nào cũng thay bằng một câu lệnh tương đương.

## 13. Kết hợp javac, jdeprscan, jdeps và runtime tests

Bốn công cụ/bước trả lời **bốn câu hỏi khác nhau**:

| Công cụ | Câu hỏi chính | Không tự làm được |
| --- | --- | --- |
| `javac -Xlint:deprecation,removal` | Source gọi API bị deprecated/forRemoval hay không? | Không phân tích mọi JAR đóng sẵn và reflection |
| `jdeprscan --release N` | Bytecode tham chiếu Java SE deprecated APIs **trong catalog N** nào? | Không bảo đảm phát hiện API đã bị xóa hoặc deprecated của tất cả thư viện ngoài |
| `javac --release N` | Source có hợp lệ với syntax/bytecode/JDK APIs của N không? | Không chứng minh mọi runtime behavior/dependency |
| `jdeps` | Phụ thuộc tĩnh, JDK internal APIs, module graph nào có thể liên quan? | Không bao quát hết dynamic loading/ServiceLoader |
| **Chạy runtime N** | Artifact thực thi được theo các luồng đã kiểm thử không? | Không chứng minh những nhánh chưa chạy và mọi platform |

Ví dụ:

~~~bash
jdeps --recursive --summary application.jar
jdeps --jdk-internals application.jar
~~~

`jdeps --jdk-internals` là bước bổ sung để phát hiện phụ thuộc vào JDK internal APIs có thể bị encapsulated hoặc thay đổi; nó **không đồng nghĩa** quét deprecated Java SE APIs.

**Một lần scan rỗng không đủ chứng minh tương thích.** Một source được biên dịch với `--release 17` có thể chứa dependency Java 21 mà bản build không đóng gói/chạy trong thử nghiệm; hoặc có plugin chỉ được gọi khi người dùng bật chức năng cụ thể.

## 14. JDK-specific APIs, thư viện ngoài và lớp nội bộ

Không phải mọi API trong một JDK đều có cùng hợp đồng hỗ trợ:

### 14.1. Java SE public API

Ví dụ `java.util.Date`, `java.util.List`, `java.time`. Tra bằng Java SE/JDK API docs theo release và compiler `--release`.

### 14.2. JDK-specific documented API

Ví dụ `com.sun.management.OperatingSystemMXBean` trong module `jdk.management` là JDK-specific API được export và document công khai. Cần tra **tài liệu module/version/vendor** cụ thể; không nên mặc định mọi Java runtime không phải JDK đều mang cùng extensions.

### 14.3. Internal APIs và encapsulation

Các lớp `sun.*` hoặc internal package không được export chính thức có thể bị module system encapsulated hoặc thay đổi. Lỗi `InaccessibleObjectException` có thể xuất phát từ vấn đề access **khác với deprecated**.

Không “sửa” mọi vấn đề bằng `--add-opens` hoặc `--add-exports` mà không hiểu chính sách module và bảo mật. Khi có public API thay thế, ưu tiên public API.

### 14.4. Third-party deprecated APIs

Một thư viện có thể tự dùng `@Deprecated` theo phiên bản của thư viện; deprecation policy của nó **không phải** deprecation catalog Java SE của `jdeprscan`. Theo dõi:

- Changelog và migration guide.
- Minimum supported Java và semantic version của library.
- Thông báo deprecated khi compile source.
- API docs của đúng dependency version.
- Tests trên dependency artifact thật.

Nếu thư viện không có replacement, đừng tự ý thay sang một thư viện khác chỉ dựa trên tên chức năng; cần so sánh semantics, giấy phép, bảo mật, compatibility và chi phí migration.

## 15. Cấu hình kiểm tra trong CI/CD

Mục tiêu CI là **không để thêm phụ thuộc deprecated mới**, đồng thời phát hiện API bị xóa trước khi nâng JDK production.

Một quy trình gợi ý:

### Bước 1 — Xác định chính xác các JDK

~~~bash
java -version
javac -version
jdeprscan --version
jdeprscan --help
~~~

Ghi vendor, version, OS, kiến trúc và đường dẫn executables tại build runner.

### Bước 2 — Build source theo minimum runtime đang cam kết

Nếu sản phẩm còn hỗ trợ Java 17:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
  -encoding UTF-8 -d out AuditOnly.java
~~~

Lệnh trong bước 2 minh họa kiểm toán từ source thử nghiệm; với dự án thật, chạy lệnh build Maven/Gradle và cấu hình lint tương ứng trên **toàn bộ source hợp lệ**.

### Bước 3 — Scan artifact đã build

~~~bash
jdeprscan --release 17 --for-removal application.jar
~~~

Thay `application.jar` bằng file JAR cuối. Quét **cả dependency classes** thuộc phạm vi trách nhiệm, không chỉ main class. Nếu thiếu dependency khi phân tích, bổ sung class path.

### Bước 4 — Quét catalog của JDK chuẩn bị nâng

Ví dụ chuẩn bị lên JDK 24:

~~~bash
jdeprscan --release 24 application.jar
jdeprscan --release 24 --for-removal application.jar
~~~

Nên dùng `jdeprscan` từ JDK 24 hoặc mới hơn **có hỗ trợ `--release 24`**. Không khẳng định danh sách này phát hiện mọi API đã bị xóa.

### Bước 5 — Check Removed APIs riêng

Đọc Removed APIs guide của JDK đích, chạy một **migration build độc lập** nhắm JDK đó và ghi lại những API compile fail; kiểm tra source/dependencies/known hotspots.

### Bước 6 — Runtime test matrix

Chạy artifact production trên **runtime tối thiểu đang cam kết** và **runtime sắp nâng**:

| Job | Compile target | Java runtime chạy test | Mục tiêu |
| --- | --- | --- | --- |
| Baseline | `--release 17` | Java 17 | Không phá minimum runtime |
| Target upgrade | Cùng artifact baseline | Java 24 | Bắt API removed, behavior và module changes |
| Migration compilation | Tạm thời dùng API target Java 24 | JDK 24 compiler | Kiểm tra source tương thích với platform API đích |
| Packaged smoke | Artifact JAR/container/app image | Runtime thật đi kèm | Kiểm tra class loading, module/native libraries |

Với Java 25/26, thay version trong các hàng tương ứng theo JDK target đã lựa chọn. Đừng tự nâng **production class major** chỉ vì muốn làm target compatibility check.

### Bước 7 — Chính sách xử lý báo cáo

Mỗi phát hiện nên ghi:

- API name/signature/module.
- Trạng thái tại baseline và target.
- `forRemoval`, `since`, hoặc bản đã removed.
- Nguồn thông tin Javadoc/JEP/migration guide.
- Vị trí trong source/dependency.
- Có replacement hay không, thay đổi semantics gì.
- Owner, độ ưu tiên, test cần thực hiện và tiêu chí hoàn thành.

**Không coi exit code 0 của scanner là “không có vấn đề”.** Trong thử nghiệm, `jdeprscan` đã in deprecations nhưng vẫn kết thúc code 0.

## 16. Mối quan hệ với Maven và Gradle

### Maven

Trong `pom.xml` có thể đặt baseline:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **mảnh cấu hình**, cần Maven Compiler Plugin phiên bản phù hợp và một JDK toolchain hỗ trợ target. Thêm compiler lint args qua cấu hình plugin ở dự án thật; **không nhầm** `maven.compiler.release=17` với việc runtime tests chắc chắn chạy bằng JVM 17.

### Gradle (Kotlin DSL)

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.compilerArgs.addAll(
        listOf("-Xlint:deprecation", "-Xlint:removal")
    )
}
~~~

Đây là **mảnh `build.gradle.kts`**, giả định dự án có Java plugin. Phải xác định toolchain JVM được Gradle chọn và có bài kiểm thử trên JDK baseline/target riêng.

### Quy tắc quản lý cảnh báo

1. Ban đầu bật lint và báo cáo.
2. Sửa những API `forRemoval=true` và các API bị xóa tại target.
3. Lên kế hoạch cho deprecated thông thường theo rủi ro.
4. Thêm gate để ngăn phát sinh mới.
5. Cân nhắc `-Werror` khi các warning đã được quản lý rõ.

Không vội gắn `@SuppressWarnings("removal")` vào hàng loạt source để làm CI “xanh” giả.

## 17. Thử nghiệm hồi quy cho việc thay API

Khi di trú từ API deprecated hoặc removed, **compile pass không đủ**. Hãy test:

### Semantics và dữ liệu

- Với ngày/giờ: năm thực, múi giờ, DST, hệ thống lịch và dữ liệu lịch sử.
- Với boxed numbers: null, identity/equality và caching nếu logic cũ từng phụ thuộc identity một cách sai lầm.
- Với concurrency: deadlocks, interrupt/cancellation, lost notification và shutdown.
- Với I/O: encoding, đường dẫn, permission, resource cleanup và exception.
- Với serialization: dữ liệu đã ghi ở bản cũ có đọc được bởi bản mới không?

### Tương thích cấu trúc

- Compile API baseline và target.
- Chạy trên Java runtime thấp nhất và target mới.
- Kiểm tra các modules cần thiết ở `jlink/jpackage` image.
- Kiểm tra dependency versions, generated code và plugin loading.
- Nếu là thư viện public, kiểm thử binary/source compatibility đối với các consumers.

### Các nhánh động

Reflection, `MethodHandles`, `ServiceLoader`, JNI và plugin discovery cần test riêng. Một class cũ không được gọi trong smoke test vẫn có thể lỗi khi một tính năng hiếm được kích hoạt.

**Tối thiểu:** bộ kiểm thử của migration phải chứng minh replacement **giữ đúng hợp đồng nghiệp vụ**, không chỉ chặn warning.

## 18. Phân loại lỗi khi nâng JDK

| Triệu chứng | Ý nghĩa khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `warning: [deprecation]` | API deprecated thông thường vẫn còn khi compile | Xem Javadoc và lên kế hoạch di trú |
| `warning: [removal]` | API còn có nhưng được đánh dấu for removal trong catalog compile | Ưu tiên sửa, không giả định ngày xóa |
| `cannot find symbol` khi compile với JDK target | API đã bị xóa, tên/overload sai hoặc classpath thiếu | Kiểm tra Javadoc target, Removed APIs và imports |
| `NoSuchMethodError` khi chạy JDK mới | Method có khi compile nhưng runtime không còn hoặc library mismatch | Phân biệt Java SE vs dependency, kiểm tra chữ ký |
| `NoClassDefFoundError` | Class bị thiếu, module/library không hiện diện, hoặc khởi tạo lỗi | Kiểm tra class loading, `Caused by`, runtime image |
| `UnsupportedClassVersionError` | Class major cao hơn runtime hỗ trợ | Kiểm tra `javap -verbose`, release target |
| `InaccessibleObjectException` | Strong encapsulation/reflection, không nhất thiết deprecated | Dùng public APIs hoặc thiết kế access đúng |
| `jdeprscan` không in gì | Không có phát hiện theo phạm vi catalog/bytecode đã scan, **không chứng minh tương thích** | Chạy compiler target, API diff và runtime tests |
| `jdeprscan` báo `cannot find class` | Thiếu dependency trong môi trường scan | Bổ sung classpath, scan lại hợp lệ |
| `jdeprscan` in cảnh báo nhưng exit code 0 | Công cụ báo phát hiện, không tự fail build | Gắn chính sách CI và phân tích báo cáo |

**Không quy mọi lỗi cho deprecated.** Một JVM upgrade có thể làm lộ lỗi runtime do file permission, TLS provider, GC settings, native libraries hoặc các thay đổi hành vi. Chỉ kết luận sau khi đối chiếu bằng chứng.

## 19. Những hiểu nhầm dễ gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Deprecated nghĩa là method đã bị xóa.” | Không. API có thể tiếp tục hoạt động nhiều bản JDK. |
| “forRemoval=true nghĩa là chắc chắn bị xóa ở bản kế tiếp.” | Chỉ thể hiện ý định; không có thời hạn bắt buộc. |
| “Không thấy trong deprecated-list thì API an toàn.” | Có thể đã bị removed, hoặc không thuộc phạm vi Java SE catalog. |
| “jdeprscan dùng để tìm tất cả API đã removed.” | Không; nó chủ yếu quét deprecated APIs trong catalog. |
| “jdeprscan không có output chắc chắn code chạy.” | Không; thiếu dynamic loading, third-party APIs, removed APIs. |
| “jdeprscan exit 0 nghĩa là không có deprecated calls.” | Scanner có thể exit 0 dù đã in findings. |
| “--release của jdeprscan và javac có cùng ý nghĩa.” | Một bên chọn deprecated catalog; bên kia chọn source/API/bytecode target. |
| “javac --release17 chứng minh code chạy trên JDK24.” | Cần test runtime24 vì API có thể bị loại bỏ sau17. |
| “-Werror chỉ chặn deprecated.” | Nó chặn **mọi warning được phát ra** trong lượt compile đó. |
| “SuppressWarnings làm API an toàn.” | Không; chỉ ảnh hưởng diagnostics, không sửa behavior/runtime. |
| “Đổi Date.getYear thành LocalDate.getYear luôn trả cùng số.” | Date.getYear trả year-1900; phải xét timezone và data contract. |
| “Integer.valueOf() luôn tạo object mới như constructor.” | Có thể caching; tránh phụ thuộc identity không đúng. |
| “Thread.resume() có replacement tương đương một dòng.” | Cần thiết kế lại lifecycle/concurrency. |
| “jdeps thay thế jdeprscan.” | Hai công cụ phục vụ mục đích phân tích khác nhau. |
| “Chỉ test main class sau khi nâng JDK.” | Dependencies, plugins, reflection và branches khác có thể lỗi. |
| “Có thể biên dịch bản target24 rồi phát hành như Java17.” | Class major24 không còn tương thích JVM17. |
| “Một cảnh báo cũ không có rủi ro vì nhiều năm chưa removed.” | Chính sách removal và runtime target vẫn có thể thay đổi. |

## 20. Checklist trước khi chấp nhận nâng JDK đích

1. **Đã xác định JDK target và minimum runtime riêng biệt chưa?**
2. **Đã xác nhận đường dẫn và version của javac/jdeprscan/runtime ở CI chưa?**
3. **Đã xem Deprecated API list của cả baseline và target chưa?**
4. **Đã xem Removed APIs guide của target chưa?**
5. **Đã phân biệt deprecated thường, forRemoval và removed chưa?**
6. **Đã bật `-Xlint:deprecation,removal` với source chưa?**
7. **Đã dùng `jdeprscan --release <supported target>` cho artifact chưa?**
8. **Scanner có báo thiếu dependency không?**
9. **Đã dùng `--for-removal` để ưu tiên những API có ý định loại bỏ chưa?**
10. **Đã compile-check API bị xóa bằng JDK đích chưa?**
11. **Đã kiểm tra third-party libraries, JDK internals và plugins riêng chưa?**
12. **Đã giữ production compiler release theo minimum-runtime policy chưa?**
13. **Đã chạy artifact thật trên JVM baseline và target chưa?**
14. **Đã test reflection/JNI/ServiceLoader và các nhánh ít dùng chưa?**
15. **Đã kiểm chứng replacement giữ đúng semantics, dữ liệu và lỗi chưa?**
16. **Đã ghi owner, priority, API replacement và bằng chứng test cho mỗi phát hiện chưa?**
17. **Đã xử lý warning bằng sửa đúng bản chất thay vì suppression đại trà chưa?**
18. **Đã kiểm tra app image/container và runtime modules thật sự khi triển khai chưa?**

## 21. Bài tập thực hành và đáp án

### Bài 1 — Deprecated không phải removed

**Đề:** `javac` in `warning: [deprecation]` nhưng compile PASS. Có nghĩa API đã bị xóa không?

**Đáp án:** không. API còn được compiler tìm thấy trong API của release đang compile, nhưng không được khuyến nghị. Xem Javadoc để hiểu lý do/replacement, và kiểm thử trên JDK target.

### Bài 2 — forRemoval không có deadline cố định

**Đề:** một method có `@Deprecated(since="17", forRemoval=true)`. Có bắt buộc Java 18 xóa nó không?

**Đáp án:** không. Annotation ghi **ý định** loại bỏ trong tương lai, không bảo đảm release xóa. Phải tra phiên bản JDK cụ thể.

### Bài 3 — Kết quả jdeprscan

**Đề:** scan `AuditOnly.class` trả hai findings, scan với `--for-removal` chỉ còn `Integer(int)`. Vì sao?

**Đáp án:** `Date.getYear()` chỉ deprecated thông thường, còn constructor `Integer(int)` mang `forRemoval=true` trong catalog đã chọn.

### Bài 4 — API đã removed không được scanner báo

**Đề:** scanner trên artifact không báo `Thread.resume()`, nhưng compile với `--release24` thất bại.

**Đáp án:** scanner quét deprecated catalog chứ không phải bộ kiểm tra mọi removed API. Xem Removed APIs guide (method bị xóa trong JDK 23), compile/test target và di trú thiết kế concurrency.

### Bài 5 — Khác nhau giữa hai --release

**Đề:** `jdeprscan --release17` và `javac --release17` có cùng chức năng?

**Đáp án:** không. Với `jdeprscan`, flag chọn danh sách deprecated của Java 17; với `javac`, nó giới hạn syntax, JDK APIs và class-file target 17.

### Bài 6 — Runtime tối thiểu không được phép thay đổi ngoài ý muốn

**Đề:** sản phẩm còn hỗ trợ Java17, nhưng bạn dùng `javac --release24` để kiểm tra removed APIs. Có nên phát hành ngay class files vừa tạo?

**Đáp án:** không. Đây là một **migration-check build riêng**; bản phát hành vẫn phải compile theo baseline17 và test runtime17 cho tới khi chính sách minimum runtime được đổi có chủ đích.

### Bài 7 — Di trú API ngày tháng

**Đề:** code cũ dùng `Date.getYear()`, người sửa thay bằng `LocalDate.getYear()` và kỳ vọng mọi giá trị bằng nhau.

**Đáp án:** sai vì method cũ trả năm **trừ 1900** và chịu ảnh hưởng timezone. Phải xác định instant, zone, cách lưu dữ liệu cũ và contract output. Năm calendar mới thường lấy bằng `date.toInstant().atZone(zoneId).getYear()`.

### Bài 8 — Bộ thư viện bên thứ ba

**Đề:** một library tự đánh dấu `@Deprecated` nhưng `jdeprscan` không báo. Có thể kết luận nó không deprecated không?

**Đáp án:** không. `jdeprscan` chủ yếu nhận diện deprecated **Java SE APIs**; với third-party library, cần compiler lint, tài liệu/changelog của chính dependency và tests.

### Bài 9 — Xác minh theo hành động

Hãy chạy ba thao tác trên JDK hỗ trợ:

1. Biên dịch `AuditOnly.java` cùng `-Xlint:deprecation,removal`.
2. Quét class bằng `jdeprscan --release17` và `--for-removal`.
3. Biên dịch `RemovedApiProbe.java` với `--release17` rồi `--release24`.

Ghi lại version tool, cảnh báo, phát hiện và compile exit codes. **Không chạy** class kiểm tra `Thread.resume()`; đây là mã audit âm tính.

### Bài 10 — Thiết kế gate CI

**Đề:** `jdeprscan` in cảnh báo nhưng exit code 0. Hãy thiết kế một gate không tạo false confidence.

**Gợi ý:** lưu machine-readable hoặc text report, so với baseline findings có chủ sở hữu, chặn các phát hiện mới theo chính sách; song song chạy `javac` lint, compile-check JDK target và runtime tests. Không chỉ kiểm tra `$LASTEXITCODE == 0` của jdeprscan.

## 22. Tài liệu chính thức hiện còn áp dụng

- [Oracle JDK 26 — Deprecated API List](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html): API deprecated và nhóm terminally deprecated trong JDK 26.
- [Oracle JDK 25 — Deprecated API List](https://docs.oracle.com/en/java/javase/25/docs/api/deprecated-list.html): danh sách và bộ lọc deprecated theo release.
- [Oracle JDK 17 — Deprecated API List](https://docs.oracle.com/en/java/javase/17/docs/api/deprecated-list.html): dùng khi baseline là Java 17.
- [Oracle JDK 25 — Removed APIs](https://docs.oracle.com/en/java/javase/25/migrate/removed-apis.html): lịch sử API Java SE thực sự bị loại bỏ, gồm Thread.resume trong JDK 23.
- [Oracle JDK 26 — Removed APIs](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html): kiểm tra khi nhắm bản mới.
- [Oracle JDK 25 — jdeprscan Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html): syntax, phạm vi Java SE, classpath, --list, --release, --for-removal.
- [Oracle JDK 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `-Xlint:deprecation`, `-Xlint:removal`, `-Werror`.
- [Oracle JDK 25 — @Deprecated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html): ngữ nghĩa `since` và `forRemoval`.
- [Oracle JDK 25 — Notifications and Warnings](https://docs.oracle.com/en/java/javase/25/core/notifications-and-warnings.html): các mức cảnh báo deprecated và removal.
- [Oracle JDK 25 — jdeps Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html): phân tích dependency và JDK internal API.
- [OpenJDK JEP 277 — Enhanced Deprecation](https://openjdk.org/jeps/277): lý do phân biệt ordinary deprecation và terminal deprecation.
