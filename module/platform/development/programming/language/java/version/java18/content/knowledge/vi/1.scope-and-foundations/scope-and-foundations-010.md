# Giới hạn nội dung ở API còn áp dụng; nhận diện tài liệu preview, incubator và cơ chế nội bộ cũ để tránh dùng sai

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Phân biệt API ổn định với API/tool đặc thù JDK, preview feature, incubator API, API deprecated và cơ chế nội bộ. Biết cách kiểm tra trạng thái của một tính năng trên JDK mục tiêu, lựa chọn API còn được hỗ trợ và loại bỏ phụ thuộc vào cờ hoặc implementation cũ. Áp dụng vào các thay đổi Java 18 vẫn hữu ích trên JDK hiện đại.

## 1. Vì sao phải kiểm tra trạng thái API trước khi học hoặc sử dụng?

Một ví dụ trên Internet có thể biên dịch được với một JDK nhưng vẫn không phù hợp để đưa vào dự án hiện tại. Tính năng đó có thể:

- Đã trở thành API ổn định và tiếp tục được hỗ trợ.
- Là API công khai của JDK nhưng không thuộc Java SE portable API.
- Chỉ được cung cấp dưới dạng preview cho một release cụ thể.
- Nằm trong một incubator module và chưa có cam kết tương thích lâu dài.
- Được đánh dấu deprecated, có thể đã lên kế hoạch loại bỏ.
- Là API nội bộ hoặc cơ chế triển khai không có hợp đồng hỗ trợ cho ứng dụng.

Những trạng thái này khác nhau. Không thể chỉ nhìn thấy một package trong JDK hoặc thấy code chạy thành công rồi kết luận đó là API nên dùng.

Với module Java 18, cần đặc biệt phân biệt:

- UTF-8 mặc định của JEP 400 và `Charset.defaultCharset()` là hành vi nền tảng/API còn áp dụng.
- Simple Web Server của JEP 408 là công cụ JDK được tài liệu hóa, nằm trong module `jdk.httpserver`.
- `{@snippet}` của JEP 413 là tính năng của Javadoc standard doclet.
- `InetAddressResolverProvider` của JEP 418 là API Java SE được đưa vào từ Java 18.
- JEP 416 thay đổi cách triển khai core reflection bên trong JDK; nó không tạo ra một API reflection mới để ứng dụng phụ thuộc.

Mục tiêu của bài không phải ghi nhớ một danh sách lịch sử preview/incubator. Mục tiêu là biết **đọc trạng thái hiện tại của API trên JDK đang dùng**, để chọn đúng hợp đồng và tránh đưa cơ chế thử nghiệm hoặc nội bộ vào mã ứng dụng.

## 2. Phân biệt các trạng thái thường gặp

### 2.1. API ổn định thuộc Java SE

Java SE API được công bố trong Java SE API Specification. Các implementation Java SE phù hợp phải tuân thủ hợp đồng của API đó.

Ví dụ:

- `java.nio.charset.Charset`
- `java.net.InetAddress`
- `java.net.spi.InetAddressResolverProvider` (từ Java 18)
- `java.lang.reflect.Method`
- `java.lang.invoke.MethodHandle`
- `java.lang.invoke.MethodHandles`
- `java.nio.file.Files`

Đây là nhóm ưu tiên khi xây dựng thư viện hoặc ứng dụng cần khả năng chạy trên nhiều implementation Java tương thích.

Tuy nhiên, API ổn định không có nghĩa mọi giá trị đầu ra đều cố định. Hợp đồng có thể bảo đảm kiểu kết quả và loại exception, trong khi địa chỉ DNS, trạng thái filesystem hoặc default charset vẫn phụ thuộc điều kiện runtime được tài liệu hóa.

### 2.2. API hoặc công cụ công khai nhưng đặc thù JDK

Một số module và công cụ được JDK công bố trong tài liệu chính thức, nhưng không thuộc Java SE API portable.

Ví dụ:

- Module `jdk.httpserver`.
- Package `com.sun.net.httpserver`.
- API `SimpleFileServer`.
- Công cụ `jwebserver`.
- Các công cụ `jlink`, `jdeps`, `jdeprscan`, `javadoc`.

Các thành phần này có thể được dùng khi dự án chủ động nhắm đến JDK cung cấp chúng và chấp nhận phạm vi phụ thuộc tương ứng.

**Tên package không đủ để xác định API nội bộ.** `com.sun.net.httpserver` nghe có vẻ là package nội bộ, nhưng đây là API JDK được tài liệu hóa trong module `jdk.httpserver`. Ngược lại, package `jdk.internal.*` là vùng nội bộ và không phải hợp đồng cho ứng dụng.

Tương tự, không phải mọi package bắt đầu bằng `jdk.` đều là nội bộ. Cần kiểm tra module summary, Javadoc và mức export của package.

### 2.3. Preview feature

Preview feature là tính năng được phát hành để người dùng thử nghiệm trong một release cụ thể trước khi quyết định hoàn thiện, thay đổi hoặc loại bỏ.

Đặc điểm quan trọng:

- Gắn với một Java release cụ thể.
- Có thể thay đổi ở release kế tiếp.
- Cần bật preview khi compile và khi chạy nếu tính năng đó yêu cầu.
- Không phải cam kết tương thích như API ổn định.
- Class file dùng preview có minor version đặc biệt và bị ràng buộc với release tương ứng.

Preview có thể là ngôn ngữ, JVM hoặc API. Không nên đồng nhất preview feature với incubator module; hai cơ chế có mục đích và cách kích hoạt khác nhau.

Ví dụ các tính năng từng trải qua preview rồi trở thành ổn định:

| Tính năng | Các release preview tiêu biểu | Trạng thái sau khi hoàn thiện |
|---|---|---|
| Records | Java 14, 15 | Final từ Java 16 |
| Sealed classes | Java 15, 16 | Final từ Java 17 |
| Pattern matching for `switch` | Java 17, 18, 19, 20 | Final từ Java 21 |
| Text blocks | Java 13, 14 | Final từ Java 15 |

Đây là ví dụ lịch sử để hiểu vòng đời. Khi dùng trên JDK hiện đại, hãy kiểm tra release mà tính năng được hoàn thiện; không bật preview chỉ vì bài viết cũ từng yêu cầu nó.

### 2.4. Incubator API/module

Incubator API là API đang được thử nghiệm trong một module có tên thường bắt đầu bằng `jdk.incubator.`.

Đặc điểm:

- API chưa có cam kết tương thích như Java SE API đã hoàn thiện.
- Có thể thay đổi chữ ký, cấu trúc hoặc hành vi giữa các release.
- Có thể được chuyển thành API ổn định, tiếp tục incubate hoặc bị loại bỏ.
- Thường cần thêm module tường minh khi compile/chạy.
- Việc module có mặt trong JDK không làm API tự động trở thành stable.

Ví dụ có thể gặp là `jdk.incubator.vector`. Hãy xác minh module và tài liệu của đúng JDK mục tiêu trước khi dùng; không suy ra trạng thái của nó ở một release mới chỉ từ bài viết cũ.

Incubator không đồng nghĩa với preview:

| Tiêu chí | Preview | Incubator |
|---|---|---|
| Phạm vi | Có thể là language, JVM hoặc API feature | API/module đang incubate |
| Nhận diện | Tài liệu/JEP đánh dấu Preview | Thường có module `jdk.incubator.*` và ghi chú Incubator |
| Bật tính năng | Dùng `--enable-preview` theo release áp dụng | Thường cần resolve module bằng `--add-modules` |
| Cam kết tương thích | Không ổn định giữa các release preview | Không có cam kết tương thích như API final |
| Điều kiện chạy | Preview compile/run phải theo đúng release | Phụ thuộc module/API có trong JDK và cách module được resolve |

Một dự án có thể gặp cả hai loại trong cùng JDK, nhưng không được dùng một cơ chế bật thay cho cơ chế còn lại.

### 2.5. API deprecated và API deprecated for removal

`@Deprecated` có nghĩa API không còn được khuyến nghị cho mã mới. API vẫn có thể còn tồn tại và vẫn có hợp đồng ở release hiện tại.

Cần phân biệt:

- `@Deprecated`: API đã bị đánh dấu không khuyến nghị.
- `@Deprecated(since = "...")`: cho biết release bắt đầu deprecated.
- `@Deprecated(forRemoval = true)`: API đã được đánh dấu có kế hoạch loại bỏ trong tương lai.
- API đã bị loại bỏ: không còn khả dụng trong JDK mục tiêu.

Deprecated không đồng nghĩa đã bị xóa. Ngược lại, việc một API vẫn biên dịch được cũng không có nghĩa nên tiếp tục dùng nó.

Khi gặp API deprecated:

1. Đọc Javadoc của đúng JDK mục tiêu.
2. Xem thuộc tính `since` và `forRemoval`.
3. Tìm API thay thế được tài liệu khuyến nghị.
4. Kiểm tra dependency và thư viện bên thứ ba còn gọi API đó không.
5. Lập kế hoạch chuyển đổi trước khi nâng JDK nếu API được đánh dấu for removal.

### 2.6. API nội bộ và implementation detail

API nội bộ là package/class không được công bố như hợp đồng hỗ trợ cho ứng dụng. Một số dấu hiệu thường gặp:

- Package `jdk.internal.*`.
- Nhiều package `sun.*`.
- Class không xuất hiện trong Java SE/JDK public API documentation.
- Package không được module export cho module ứng dụng.
- Cơ chế phụ thuộc vào reflection để truy cập field/method private của JDK.

Không phải mọi API có tên `com.sun.*` đều nội bộ; cần kiểm tra tài liệu và module. Nhưng với `sun.*` và `jdk.internal.*`, hãy mặc định không dùng cho mã ứng dụng cho tới khi tài liệu chính thức chứng minh ngược lại.

Implementation detail có thể thay đổi theo vendor, patch hoặc release mà không phải duy trì tương thích cho ứng dụng. Việc dùng reflection để truy cập được một class nội bộ không biến nó thành public API.

Một ví dụ cần nhận diện khi nâng JDK là các phương thức truy cập bộ nhớ của `sun.misc.Unsafe`. JEP 471 đánh dấu các phương thức memory-access này deprecated for removal từ JDK 23. Với nhu cầu truy cập biến có kiểm soát, xem `VarHandle`; với tương tác bộ nhớ/native memory ngoài heap, đánh giá Foreign Function & Memory API đã được hoàn thiện trong JDK 22. Chọn thay thế theo đúng semantics cần thiết, không thay bằng một API khác chỉ vì tên có vẻ tương đương.

## 3. Cách xác định trạng thái của API trên JDK mục tiêu

### 3.1. Tra cứu Java SE API và JDK API documentation

Bắt đầu bằng câu hỏi: API có nằm trong tài liệu Java SE API hay chỉ có trong JDK API documentation?

Ví dụ:

- `InetAddressResolverProvider` nằm trong Java SE API của `java.base`.
- `Method.invoke` nằm trong Java SE API của `java.base`.
- `com.sun.net.httpserver.SimpleFileServer` nằm trong JDK API của `jdk.httpserver`.
- `jwebserver` được mô tả trong JDK tool specification.

Khi mở Javadoc, kiểm tra:

- Module chứa API.
- Package và class summary.
- `Since`.
- `Deprecated`.
- `Preview` hoặc ghi chú incubator nếu có.
- `Throws`, `Returns`, `Implementation Requirements` và các API note.
- Trạng thái export của package và module dependency.

Không dùng một bài blog hoặc một ví dụ Stack Overflow làm nguồn duy nhất để kết luận API còn được hỗ trợ.

### 3.2. Kiểm tra module hiện có trong JDK

Trên Linux/macOS:

~~~shell
java --list-modules | grep -E '^(java.base|jdk.httpserver|jdk.incubator)'
~~~

Trên Windows PowerShell:

~~~powershell
java --list-modules |
    Select-String '^(java\.base|jdk\.httpserver|jdk\.incubator)'
~~~

Lệnh này cho biết các module hiện diện trong runtime image đang được gọi. Nếu cần mô tả một module:

~~~shell
java --describe-module jdk.httpserver
~~~

Với module incubator, thay tên bằng module cụ thể:

~~~shell
java --describe-module jdk.incubator.vector
~~~

Nếu không tìm thấy module, có thể JDK hoặc custom runtime image đang dùng không chứa module đó. Không tự cài thêm một JAR bất kỳ có cùng tên để thay thế module của JDK.

### 3.3. Phân biệt module có mặt với module đã được resolve

`java --list-modules` cho biết module quan sát được trong runtime image. Nó không tự chứng minh module đã được resolve vào module graph của một ứng dụng cụ thể.

Để quan sát module graph khi chạy ứng dụng:

~~~shell
java --show-module-resolution -m com.example.app/com.example.app.Main
~~~

Thay tên module và main class bằng dự án thực tế. Nếu ứng dụng dùng API từ một module JDK cụ thể, kiểm tra module đó có mặt và được resolve theo cấu hình khởi chạy.

### 3.4. Xác định package được export

Dùng:

~~~shell
java --describe-module java.base
java --describe-module jdk.httpserver
~~~

Output mô tả module, các package export/open, service và dependency. Đây là cách phân biệt một package JDK được công bố với package nội bộ.

Ví dụ `com.sun.net.httpserver` được export bởi `jdk.httpserver`. Điều đó cho phép ứng dụng dùng API đã tài liệu hóa của module này khi module được resolve; nó không biến module đó thành Java SE API portable.

### 3.5. Dùng công cụ rà soát dependency

`jdeps` có thể phát hiện tham chiếu tĩnh tới JDK internal API:

~~~shell
jdeps --jdk-internals --recursive app.jar
~~~

Kết quả giúp xác định class/package nội bộ mà bytecode tham chiếu. Tuy nhiên, phân tích tĩnh có thể bỏ sót truy cập qua reflection, tên class lấy từ cấu hình, JNI hoặc code được tải động. Cần kết hợp tìm kiếm source, cấu hình, dependency và test runtime.

`jdeprscan` giúp rà soát việc sử dụng API deprecated:

~~~shell
jdeprscan --release 27 app.jar
~~~

Thay `27` bằng release JDK mục tiêu. Công cụ báo các tham chiếu deprecated mà nó nhận diện được; không coi kết quả rỗng là bằng chứng mọi API đều portable hoặc không có truy cập nội bộ qua reflection.

## 4. Sử dụng preview feature đúng release

### 4.1. Bật preview khi compile

Nếu đang thử một preview feature của chính JDK 27, ví dụ lệnh tổng quát:

~~~shell
javac --enable-preview --release 27 PreviewExample.java
~~~

`--enable-preview` yêu cầu compiler cho phép preview feature của release tương ứng. Không dùng `--enable-preview` như một cờ chung để bật tính năng incubator hoặc mở package nội bộ.

Với compiler JDK 27, không thể dùng cờ này để biên dịch preview feature của Java 25 như thể đó là preview feature hiện hành. Hãy dùng JDK tương ứng để thử preview của release đó, hoặc đợi tính năng được hoàn thiện.

### 4.2. Bật preview khi chạy

Nếu class được biên dịch với preview của Java 27, chạy bằng runtime cùng release và bật preview:

~~~shell
java --enable-preview PreviewExample
~~~

Không giả định một JVM release mới hơn sẽ chạy class file preview của release cũ. Class file preview mang minor version `65535` và bị ràng buộc với release đã tạo ra nó.

### 4.3. Không dùng preview làm baseline thư viện ổn định

Preview phù hợp để:

- Thử nghiệm trong dự án có chủ đích.
- Đánh giá thiết kế trước khi tính năng final.
- Thử nghiệm nội bộ với toolchain/runtime đã ghim release.
- Cung cấp feedback trong giai đoạn preview.

Preview không phù hợp làm baseline mặc định cho thư viện cần tương thích rộng hoặc artefact phát hành dài hạn. Nếu một preview feature đã trở thành final, dùng cú pháp/API final theo release hoàn thiện và bỏ `--enable-preview` nếu không còn preview nào khác.

## 5. Sử dụng incubator module có kiểm soát

### 5.1. Nhận diện module incubator

Tìm các module có tên `jdk.incubator.*`:

~~~shell
java --list-modules | grep incubator
~~~

Trên PowerShell:

~~~powershell
java --list-modules | Select-String 'incubator'
~~~

Sau đó tra module summary và release note của đúng JDK. Tên module chỉ là dấu hiệu ban đầu; tài liệu chính thức mới xác nhận trạng thái và phạm vi API.

### 5.2. Resolve module khi compile/chạy

Một ví dụ tổng quát khi JDK mục tiêu có module incubator:

~~~shell
javac --add-modules jdk.incubator.vector Example.java
java --add-modules jdk.incubator.vector Example
~~~

Tên module chỉ là ví dụ; hãy dùng tên module thực sự có trong JDK được cài. Một số API có thể yêu cầu module path hoặc dependency khác theo tài liệu.

`--add-modules` chỉ yêu cầu module resolver đưa module vào graph. Nó không biến API incubator thành API final, không bỏ cảnh báo incubator và không tạo cam kết tương thích giữa các release.

### 5.3. Đánh giá rủi ro trước khi phụ thuộc

Trước khi đưa incubator API vào ứng dụng:

1. Xác định tính năng có thực sự cần thiết không.
2. Đọc module summary và Javadoc của release mục tiêu.
3. Ghi rõ JDK vendor/version và module dependency.
4. Đặt abstraction trong ứng dụng để hạn chế phạm vi API thử nghiệm.
5. Có implementation thay thế nếu dự án cần chạy trên JDK không có module.
6. Theo dõi release notes/JEP khi nâng JDK.
7. Chạy test tương thích sau mỗi lần đổi release.

Không đưa incubator API vào public library API nếu chưa chấp nhận rằng consumer phải phụ thuộc đúng JDK/module tương ứng.

## 6. Tránh API nội bộ và cơ chế mở module cũ

### 6.1. Vì sao internal API gây rủi ro?

Ví dụ một ứng dụng truy cập `jdk.internal.*` hoặc `sun.*` có thể:

- Không compile được trên JDK khác.
- Không chạy được sau khi module encapsulation được tăng cường.
- Gặp lỗi access check hoặc reflection.
- Phụ thuộc vào field/method nội bộ bị đổi tên hoặc xóa.
- Không được hỗ trợ khi đổi vendor hoặc nâng patch.

API nội bộ không có cùng cam kết tương thích như API Java SE hoặc JDK public API. Đừng đưa nó vào thiết kế mới chỉ vì một bài benchmark cho thấy nhanh hơn hoặc một thư viện cũ đang dùng.

### 6.2. Strong encapsulation và cờ `--illegal-access`

Từ Java 9, JPMS kiểm soát package export/open. JDK 16 chuyển sang mặc định strong encapsulation cho nhiều internal package; từ JDK 17, cơ chế nới lỏng hàng loạt qua `--illegal-access` không còn tác dụng.

Vì vậy:

- Không hướng dẫn người học thêm `--illegal-access=permit` để sửa ứng dụng trên JDK hiện đại.
- Không xem việc lệnh Java vẫn nhận một option cũ là bằng chứng option đó còn mở quyền truy cập.
- Tìm dependency hoặc thư viện cũ đang truy cập internals và nâng cấp/thay thế chúng.

### 6.3. Phân biệt `--add-exports` và `--add-opens`

Hai cờ này có mục đích khác nhau và chỉ nên dùng như biện pháp chuyển tiếp có chủ đích.

| Cờ | Mục đích | Phạm vi |
|---|---|---|
| `--add-exports module/package=target` | Cho module đích truy cập public type trong package chưa export | Truy cập kiểu public ở compile/runtime tùy vị trí dùng cờ |
| `--add-opens module/package=target` | Mở package cho deep reflection vào member không public | Runtime reflection |

Ví dụ cú pháp tổng quát:

~~~shell
java --add-opens java.base/java.lang=ALL-UNNAMED App
~~~

Lệnh này mở package `java.lang` của module `java.base` cho code trên classpath (unnamed module) thực hiện deep reflection. Nó không biến private member thành public API và không tạo cam kết rằng tên/cấu trúc member sẽ giữ nguyên ở JDK tiếp theo.

Nếu buộc phải dùng cờ:

1. Xác định chính xác thư viện nào cần quyền.
2. Mở đúng package và đúng module đích.
3. Ghi lý do, phạm vi và release đang hỗ trợ.
4. Cập nhật dependency để bỏ cờ khi có bản sửa.
5. Kiểm thử lại khi nâng JDK.

Không thêm `ALL-UNNAMED` cho hàng loạt package chỉ để làm ứng dụng cũ chạy mà không biết dependency nào cần quyền.

### 6.4. Không dùng SecurityManager làm sandbox mới

SecurityManager đã bị deprecated for removal và được vô hiệu hóa vĩnh viễn từ JDK 24. Không thiết kế cơ chế sandbox mới dựa trên SecurityManager hoặc policy file cũ. Với yêu cầu cô lập tiến trình, đánh giá cơ chế ở cấp OS/container, quyền tài khoản, filesystem, network và process boundary phù hợp.

Đây là ví dụ về cơ chế từng là một phần của nền tảng nhưng không còn là lựa chọn khả dụng trên JDK hiện đại.

## 7. Phân biệt JEP 416 với API reflection mà ứng dụng được phép dùng

JEP 416 tái triển khai core reflection bằng method handles trong JDK 18. Thay đổi này nằm ở implementation của JDK.

Các API public vẫn có hợp đồng riêng:

- `java.lang.reflect.Method`.
- `Method.invoke()`.
- `java.lang.invoke.MethodHandle`.
- `MethodHandles.lookup()`.
- `MethodHandle.invokeExact()`.

Ví dụ:

~~~java
Method method = Service.class.getMethod("execute");
try {
    method.invoke(service);
} catch (InvocationTargetException exception) {
    Throwable targetFailure = exception.getCause();
}
~~~

Ứng dụng có thể dựa vào hợp đồng `InvocationTargetException` và cause. Ứng dụng không được dựa vào việc JDK dùng một class nội bộ cụ thể để lưu `Method`, một object layout nhất định hoặc một call path reflection nhất định.

Không dùng cờ/thuộc tính nội bộ của một JDK cũ để ép runtime hiện đại quay lại implementation reflection cũ. Nếu một framework cần quyền truy cập sâu, xử lý module access theo API được hỗ trợ và nâng framework lên phiên bản tương thích với JDK mục tiêu.

## 8. Phân loại trạng thái của các thay đổi Java 18

Bảng này giúp chọn đúng loại tài liệu và cách kiểm tra:

| Thay đổi | Thành phần hiện hành | Phân loại | Cách sử dụng |
|---|---|---|---|
| JEP 400 — UTF-8 by Default | `Charset.defaultCharset()` và default charset behavior | Java SE API + platform behavior | Dùng API public, ghi runtime options và chỉ định charset explicit cho dữ liệu có định dạng cố định |
| JEP 408 — Simple Web Server | `jwebserver`, `SimpleFileServer`, `jdk.httpserver` | JDK documented tool/API | Dùng cho static file development/test; ghi JDK/module dependency |
| JEP 413 — Javadoc snippet | `{@snippet}` và standard doclet | JDK tool/documentation feature | Dùng Javadoc của JDK hỗ trợ; test render riêng với compile/test code |
| JEP 418 — Resolver SPI | `InetAddressResolverProvider`, `InetAddressResolver` | Java SE API từ Java 18 | Dùng provider SPI public; kiểm soát service registration và DNS test |
| JEP 416 — Core reflection | `Method`, `MethodHandle` và reflection runtime | Public API ổn định + implementation change | Dựa vào public contract; không truy cập reflection internals |

Điểm cần nhớ:

- Không phải JEP nào cũng tạo ra API mới.
- JEP có thể thay đổi implementation mà không đổi public API.
- Một công cụ JDK được tài liệu hóa không nhất thiết là Java SE API.
- Một API có mặt trong JDK mới không có nghĩa nó đã tồn tại trong release cũ.
- `--release N` kiểm tra source/API platform và class file của release N; nó không tự chứng minh một API là Java SE portable thay vì JDK-specific.

## 9. Phân biệt `--release` với trạng thái ổn định của API

`javac --release N` hữu ích để giữ baseline compile ở release N:

~~~shell
javac --release 18 Example.java
~~~

Tùy chọn này kiểm tra source language, class file target và API Java SE cùng các JDK API được export cho release N.

Nhưng `--release` không tự trả lời:

- API có thuộc Java SE hay chỉ thuộc JDK không?
- API có bị deprecated không?
- API có phải incubator/preview không?
- Ứng dụng có phụ thuộc internal API qua reflection không?
- Tool đang gọi có đến từ đúng JDK không?
- Runtime thực tế có module và provider cần thiết không?

Vì thế, kiểm tra `--release` phải đi cùng Javadoc/module inspection và rà dependency.

Ví dụ: `jdk.httpserver` là module JDK được tài liệu hóa. Nếu ứng dụng dùng `com.sun.net.httpserver`, cần ghi rõ đây là dependency JDK-specific dù compiler có thể biên dịch thành công với release phù hợp.

## 10. Quy trình rà soát dependency trước khi nâng JDK

Khi nâng từ một JDK cũ lên JDK hiện đại, thực hiện lần lượt:

1. **Ghi baseline:** JDK vendor/version hiện tại và JDK đích.
2. **Compile sạch:** build từ source, không tái sử dụng class file cũ.
3. **Chọn release:** đặt `--release` theo mức API thấp nhất mà dự án cam kết hỗ trợ.
4. **Rà internal API:** chạy `jdeps --jdk-internals` trên ứng dụng và dependency.
5. **Rà deprecated API:** chạy `jdeprscan` theo release đích và kiểm tra `forRemoval`.
6. **Rà preview/incubator:** tìm `--enable-preview`, `jdk.incubator.*`, module flags và annotation/status trong tài liệu.
7. **Rà module access:** tìm `--add-exports`, `--add-opens`, `--illegal-access` trong script, IDE, service file và container config.
8. **Nâng dependency:** cập nhật framework/library có truy cập internals hoặc yêu cầu module mở.
9. **Kiểm tra runtime:** chạy trên đúng JDK/vendor/OS mục tiêu và xác minh module graph.
10. **Xóa cờ chuyển tiếp:** chỉ giữ cờ nào còn có lý do cụ thể và đã được kiểm thử.
11. **Chạy test:** unit, integration, startup, serialization, network, reflection và smoke tests cần thiết.
12. **Ghi lại quyết định:** API được chọn, API bị loại, lý do và release hỗ trợ.

Không chỉ sửa source. Một cờ JVM có thể được khai báo trong `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Maven/Gradle, service unit, Dockerfile hoặc cấu hình IDE. Cần rà toàn bộ nơi khởi chạy ứng dụng.

## 11. Tìm dấu hiệu cũ trong repository và cấu hình

Có thể tìm các dấu hiệu thường gặp bằng ripgrep:

~~~shell
rg -n --hidden -g '!target' -g '!build' -g '!out' \
  'jdk\.internal\.|sun\.|--illegal-access|--add-exports|--add-opens|--enable-preview|jdk\.incubator\.' .
~~~

Đây là bước sàng lọc, không phải phán quyết:

- Kết quả `sun.` có thể là import nội bộ, nhưng cũng có thể chỉ là chuỗi hoặc tài liệu.
- `--add-opens` có thể đang phục vụ một thư viện cũ; cần tìm owner và lý do.
- `--enable-preview` có thể được dùng hợp lệ cho một dự án thử nghiệm được ghim JDK.
- `jdk.incubator.*` có thể là dependency có chủ đích và cần đánh giá lộ trình thay thế.

Tiếp tục kiểm tra từng kết quả trong source/build/runtime configuration. Không xóa hàng loạt cờ hoặc dependency mà không hiểu tác dụng của chúng.

### 11.1. Kiểm tra annotation deprecation trong source

Tìm `@Deprecated` trong source hoặc đọc Javadoc của API được gọi. Chú ý:

~~~java
@Deprecated(since = "25", forRemoval = true)
public void oldOperation() {
    // ...
}
~~~

Đây là ví dụ minh họa annotation, không phải API Java cụ thể. `forRemoval=true` là tín hiệu cần lập kế hoạch chuyển đổi; không đợi đến lúc JDK xóa API mới xử lý.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Preview và incubator là một | Preview gắn với feature/release; incubator là API/module đang thử nghiệm |
| Có `--enable-preview` là bật mọi tính năng thử nghiệm | Cờ chỉ áp dụng preview feature của release compiler/runtime tương ứng |
| Module `jdk.incubator.*` có trong JDK nghĩa là stable | Module hiện diện không tạo cam kết tương thích |
| Deprecated nghĩa là đã bị xóa | Deprecated API có thể còn tồn tại; xem `forRemoval` và release |
| Package `com.sun.*` luôn là internal | Kiểm tra tài liệu/module; `com.sun.net.httpserver` là JDK documented API |
| Package `jdk.*` luôn là internal | Một số module JDK có public API được tài liệu hóa |
| `--add-opens` biến private API thành public | Nó chỉ mở quyền deep reflection cho target module |
| `--add-exports` giống `--add-opens` | Một cờ export public type, một cờ mở deep reflection |
| `--illegal-access=permit` sửa được mọi lỗi trên JDK mới | Cơ chế nới lỏng hàng loạt này không còn tác dụng từ JDK 17 |
| `--release 18` chứng minh mọi dependency portable | Nó giới hạn compile API của release, không phân loại mọi dependency thành Java SE |
| JEP 416 yêu cầu ứng dụng gọi MethodHandle thay cho reflection | JEP 416 thay implementation core reflection; chọn public API theo nhu cầu ứng dụng |

## 13. Thiết kế chính sách API cho dự án

Một dự án nên ghi rõ mức phụ thuộc được chấp nhận:

| Nhóm | Chính sách gợi ý |
|---|---|
| Java SE API ổn định | Mặc định được dùng |
| JDK documented API/tool | Được dùng khi đã chấp nhận vendor/JDK dependency và ghi rõ trong kiến trúc |
| Preview feature | Chỉ dùng trong thử nghiệm hoặc sản phẩm có release/runtime được ghim và kế hoạch nâng cấp |
| Incubator API | Chỉ dùng khi lợi ích rõ, có abstraction và kế hoạch thay thế |
| Deprecated API | Không thêm mới; có kế hoạch migrate theo mức rủi ro |
| Deprecated for removal | Ưu tiên loại bỏ sớm, theo dõi release đích |
| Internal API | Không dùng trong mã ứng dụng mới; xử lý dependency cũ |
| Implementation detail | Không dùng làm hợp đồng hoặc assertion portable |

Đối với thư viện public, tiêu chuẩn nên chặt hơn ứng dụng nội bộ: ưu tiên Java SE API và tránh để kiểu dữ liệu incubator/JDK-specific lộ ra public signature nếu consumer cần tương thích rộng.

## 14. Bài thực hành

### Bài 1 — Phân loại API của Java 18

Tra cứu `Charset.defaultCharset`, `InetAddressResolverProvider`, `Method.invoke`, `SimpleFileServer` và công cụ `jwebserver`.

**Tiêu chí đạt:** Xác định được API nào thuộc Java SE, thành phần nào là JDK-specific và JEP nào chỉ thay implementation.

### Bài 2 — Kiểm tra module incubator

Chạy `java --list-modules`, tìm `jdk.incubator.*`, mô tả một module đang có bằng `--describe-module` và đọc Javadoc của đúng release.

**Tiêu chí đạt:** Không kết luận module stable chỉ vì nó có mặt; giải thích được khác biệt giữa incubator và preview.

### Bài 3 — Thử preview có kiểm soát

Chọn một preview feature của JDK hiện hành, compile và chạy với `--enable-preview` theo cùng release. Sau đó tìm một feature từng preview nhưng đã final để so sánh.

**Tiêu chí đạt:** Hiểu release lock của preview và biết bỏ cờ khi dùng feature đã final.

### Bài 4 — Rà internal/deprecated dependency

Chạy `jdeps --jdk-internals` và `jdeprscan` trên một JAR mẫu. Đối chiếu kết quả với source/Javadoc.

**Tiêu chí đạt:** Biết giới hạn phân tích tĩnh; phân biệt internal API với deprecated API.

### Bài 5 — Rà cờ JVM cũ

Tìm `--illegal-access`, `--add-exports`, `--add-opens` và `--enable-preview` trong cấu hình dự án. Xác định cờ nào cần, cờ nào lỗi thời và dependency nào nên nâng cấp.

**Tiêu chí đạt:** Không xóa cờ một cách máy móc; đưa ra lý do và kế hoạch bỏ từng cờ.

## 15. Checklist trước khi chọn một API

- [ ] Đã xác định API thuộc Java SE hay JDK-specific.
- [ ] Đã kiểm tra module và package export.
- [ ] Đã đọc Javadoc của đúng JDK release.
- [ ] Đã kiểm tra preview/incubator status.
- [ ] Đã xem `@Deprecated`, `since` và `forRemoval`.
- [ ] Đã rà package `jdk.internal.*` và `sun.*`.
- [ ] Đã kiểm tra các cờ `--illegal-access`, `--add-exports`, `--add-opens`.
- [ ] Đã xác định API có cần `--enable-preview` hoặc `--add-modules` không.
- [ ] Đã kiểm tra API baseline bằng `--release`.
- [ ] Đã chạy test trên runtime/vendor mục tiêu.
- [ ] Đã ghi rõ JDK-specific dependency trong kiến trúc.
- [ ] Không dựa vào implementation detail làm hợp đồng ứng dụng.

## 16. Tài liệu chính thức

1. [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/): phân biệt API thuộc Java SE và module nền tảng.
2. [JEP 12 — Preview Features](https://openjdk.org/jeps/12): mục đích và vòng đời preview feature.
3. [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11): mô hình incubator module.
4. [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--enable-preview`, `--release` và compile options.
5. [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): runtime preview option, module resolution và launcher.
6. [The jdeps Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): phát hiện dependency tới JDK internals.
7. [The jdeprscan Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html): rà soát deprecated API.
8. [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation và thay đổi `--illegal-access`.
9. [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): trạng thái SecurityManager từ JDK 24.
10. [JEP 471 — Deprecate the Memory-Access Methods of sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471): ví dụ về internal/unsupported low-level API cần chuyển đổi.
11. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): trạng thái default charset.
12. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): công cụ JDK được tài liệu hóa.
13. [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): snippet trong standard doclet.
14. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): API resolver ổn định từ Java 18.
15. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): implementation change của core reflection.
16. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API tương tác native memory đã được hoàn thiện trong JDK 22.

**Kết quả cần đạt:** Khi gặp một ví dụ Java, bạn có thể xác định nó dùng API Java SE ổn định, API/tool đặc thù JDK, preview feature, incubator module, deprecated API hay internal implementation. Bạn biết cách kiểm tra trạng thái trên JDK mục tiêu, hiểu giới hạn của từng cơ chế và chọn API còn được hỗ trợ để xây dựng ứng dụng có thể nâng cấp an toàn.
