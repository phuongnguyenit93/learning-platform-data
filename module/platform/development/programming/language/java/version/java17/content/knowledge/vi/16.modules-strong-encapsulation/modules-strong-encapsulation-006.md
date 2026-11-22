# Phát hiện phụ thuộc nội bộ bằng jdeps --jdk-internals trong Java 17

**Chủ đề:** Java 17 → Module và đóng gói mạnh  
**Trọng tâm:** Dùng công cụ `jdeps` với tùy chọn `--jdk-internals` để tìm những lớp trong ứng dụng hoặc thư viện đang phụ thuộc vào API nội bộ của JDK; đọc kết quả, hiểu giới hạn phân tích tĩnh và lập kế hoạch thay thế bằng API được hỗ trợ.

Java 17 đóng gói mạnh các thành phần nội bộ của JDK theo hệ thống module. Một số lớp hoặc thư viện từng truy cập được các package nội bộ có thể không còn hoạt động khi chạy trên Java 17. Để tìm những phụ thuộc này trước khi phát hành, JDK cung cấp công cụ `jdeps`. Tùy chọn `--jdk-internals` (tên ngắn `-jdkinternals`) tìm các phụ thuộc cấp lớp vào API nội bộ của JDK và có thể đưa ra gợi ý thay thế.

`jdeps` phân tích bytecode đã biên dịch, không phân tích trực tiếp mã nguồn `.java` và cũng không chạy ứng dụng. Vì vậy, đây là một bước kiểm tra quan trọng trong quá trình nâng cấp JDK, nhưng không thay thế việc kiểm thử ứng dụng trên Java 17.

## 1. API nội bộ của JDK là gì?

JDK có nhiều lớp và package phục vụ chính việc triển khai nền tảng. Một số lớp từng được ứng dụng hoặc thư viện bên thứ ba sử dụng trực tiếp dù chúng không thuộc API Java SE được hỗ trợ công khai.

Một phụ thuộc như vậy có rủi ro vì:

- Tên lớp, phương thức, trường hoặc cấu trúc nội bộ có thể thay đổi giữa các bản JDK.
- Package có thể bị đóng gói trong module và không còn được export cho mã ứng dụng.
- Thành phần có thể bị loại bỏ khi JDK phát triển.
- Hành vi nội bộ không có cam kết tương thích như API công khai.
- Ứng dụng có thể biên dịch được trên một JDK nhưng không liên kết hoặc không chạy được trên JDK khác.

Không phải mọi package có tiền tố `com.sun` hoặc `sun` đều có thể được phân loại chỉ bằng cách nhìn tên. Có một số API đặc biệt được export để hỗ trợ hệ sinh thái, trong khi nhiều package cùng namespace vẫn là nội bộ. Hãy dùng `jdeps` và tài liệu JDK để xác định phụ thuộc cụ thể, thay vì tự kết luận chỉ từ tiền tố package.

### 1.1. Strong encapsulation trong Java 17

Java Platform Module System được giới thiệu từ Java 9. Module có thể export những package được phép truy cập công khai; các package không export được đóng gói khỏi mã bên ngoài.

Trong Java 17, JEP 403 hoàn tất việc **strongly encapsulate các thành phần nội bộ của JDK theo mặc định**. Một số API quan trọng, ví dụ `sun.misc.Unsafe`, vẫn là ngoại lệ được export trong module `jdk.unsupported`, nhưng điều đó không biến chúng thành API Java SE được hỗ trợ ổn định.

Vì vậy cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| API công khai, được hỗ trợ | Có hợp đồng API và cam kết tương thích theo chính sách của nền tảng. |
| API nội bộ đã bị đóng gói | Mã ngoài module không thể truy cập package đó theo cách thông thường. |
| API nội bộ còn được export như ngoại lệ | Có thể vẫn truy cập trong một số cấu hình, nhưng không có cam kết tương thích như API công khai. |
| API đã bị loại bỏ | Không còn có mặt trong JDK mục tiêu; phụ thuộc có thể gây lỗi liên kết hoặc lỗi runtime. |

`jdeps --jdk-internals` giúp tìm tham chiếu bytecode đến nhóm API nội bộ. Nó không bảo đảm rằng mọi tham chiếu đều gây lỗi ngay khi chạy Java 17; một số API ngoại lệ vẫn có thể truy cập. Kết quả vẫn cần được xử lý vì phụ thuộc vào chi tiết triển khai JDK là rủi ro nâng cấp.

## 2. jdeps là công cụ gì?

`jdeps` là Java Dependency Analysis Tool, đi kèm JDK. Công cụ phân tích dependency của các file class, thư mục class hoặc JAR, ở cấp package hoặc cấp lớp.

Các dạng đầu vào phổ biến:

- Một file `.class`.
- Một thư mục chứa các file class đã biên dịch.
- Một file JAR.
- Một nhóm JAR hoặc class path của ứng dụng.
- Module hoặc module path khi phân tích ứng dụng modular.

Tùy chọn `--jdk-internals` yêu cầu `jdeps` tìm các **class-level dependencies** tới API nội bộ JDK. Kết quả thường cho biết:

1. Artifact hoặc module nào chứa lớp đang phân tích.
2. Lớp ứng dụng nào tham chiếu tới lớp nội bộ.
3. Tên API nội bộ được tham chiếu.
4. Module JDK chứa package đó, nếu xác định được.
5. Bảng gợi ý thay thế khi JDK có thông tin tương ứng.

`jdeps` nằm trong thư mục `bin` của JDK. Nếu `JAVA_HOME` trỏ đến JDK 17 và thư mục `bin` nằm trong `PATH`, có thể chạy:

~~~shell
jdeps --version
jdeps --help
~~~

Trên Windows PowerShell, nếu chưa thêm JDK vào `PATH`:

~~~powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --version
~~~

Hãy kiểm tra công cụ đang chạy thuộc JDK nào. Khi phân tích ứng dụng dành cho Java 17, nên dùng `jdeps` của JDK 17 để kết quả phản ánh module và API của phiên bản đích.

## 3. Cú pháp cơ bản của --jdk-internals

Cú pháp thường dùng:

~~~shell
jdeps --jdk-internals path
~~~

Ví dụ:

~~~shell
jdeps --jdk-internals build/classes
jdeps --jdk-internals build/libs/application.jar
jdeps --jdk-internals target/application.jar
~~~

Tùy chọn `--jdk-internals` có alias ngắn `-jdkinternals`:

~~~shell
jdeps -jdkinternals build/libs/application.jar
~~~

Trong script mới, nên ưu tiên tên dài `--jdk-internals` vì dễ đọc và thể hiện rõ mục đích.

Theo tài liệu JDK 17:

- Tùy chọn này tìm phụ thuộc cấp lớp tới JDK internal APIs.
- Mặc định, công cụ phân tích các lớp trong các file đầu vào và các lớp được chỉ định qua `--class-path`, trừ khi giới hạn tập lớp bằng `-include`.
- Tùy chọn này không kết hợp với `-p`, `-e` và `-s`.

`--jdk-internals` không phải lệnh sửa mã. Nó phát hiện dependency và báo cáo để nhóm phát triển quyết định cách thay thế.

## 4. Ví dụ: tìm tham chiếu đến một API nội bộ

Để minh họa công cụ, có thể tạo một lớp tham chiếu tới `sun.misc.Unsafe`. Đây là một API nội bộ đặc biệt vẫn được export trong JDK 17 qua module `jdk.unsupported`. Nó **không phải lựa chọn nên dùng cho mã ứng dụng mới**; ví dụ chỉ giúp tạo một dependency có thể quan sát bằng `jdeps`.

Tạo file `src/UnsafeReference.java`:

~~~java
import sun.misc.Unsafe;

public final class UnsafeReference {
    private static Unsafe unsafe;
}
~~~

Biên dịch bằng JDK 17:

~~~shell
javac -d out src/UnsafeReference.java
~~~

Trình biên dịch có thể đưa ra cảnh báo rằng `Unsafe` là API nội bộ độc quyền của JDK. Vì `sun.misc` được export qua `jdk.unsupported`, ví dụ tham chiếu này có thể biên dịch trên JDK 17 mà không cần mở một package khác bằng cờ bổ sung.

Chạy phân tích:

~~~shell
jdeps --jdk-internals out
~~~

Kết quả có dạng minh họa:

~~~text
out -> jdk.unsupported
   UnsafeReference -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your
application.
~~~

Phần tên artifact, lớp và định dạng cảnh báo có thể khác theo đầu vào và bản JDK. Điểm cần đọc là:

- `UnsafeReference` là lớp của ứng dụng có tham chiếu nội bộ.
- `sun.misc.Unsafe` là API nội bộ được phát hiện.
- `jdk.unsupported` là module chứa package này.

Một kết quả như vậy vẫn đáng xử lý dù package hiện được export. API nội bộ không có bảo đảm tương thích tương đương API công khai; việc một ứng dụng chạy được hôm nay không bảo đảm các phương thức nó dùng sẽ tiếp tục được hỗ trợ ở những bản JDK sau.

## 5. Đọc bảng Suggested Replacement

Khi có thông tin thay thế, `jdeps` có thể in bảng:

~~~text
JDK Internal API                 Suggested Replacement
----------------                 ---------------------
<internal API>                   <replacement or migration reference>
~~~

Bảng này là **gợi ý điều tra**, không phải một bản vá tự động:

- Có API nội bộ có một API chuẩn thay thế trực tiếp.
- Có API cần thay đổi cách thiết kế hoặc cách truy cập dữ liệu.
- Có API không có một thay thế tương đương duy nhất.
- Một gợi ý có thể trỏ tới JEP hoặc tài liệu migration thay vì tên lớp thay thế.

Đừng chỉ thay tên import rồi cho rằng migration đã xong. Hãy so sánh hành vi, mô hình đồng bộ, hiệu năng, quyền truy cập và các trường hợp biên của API cũ với API chuẩn.

### 5.1. Ví dụ với Unsafe

`sun.misc.Unsafe` vẫn tồn tại như một ngoại lệ quan trọng trong Java 17, nhưng các phương thức của nó là API nội bộ, không phải hợp đồng công khai được hỗ trợ lâu dài.

Nếu mã dùng `Unsafe` để đọc, ghi hoặc thực hiện thao tác nguyên tử trên field/array, có thể đánh giá `java.lang.invoke.VarHandle`. `VarHandle` là API chuẩn từ Java 9, cho phép truy cập biến với các chế độ bộ nhớ và thao tác nguyên tử được xác định.

Ví dụ một bộ đếm dùng VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }

    public int get() {
        return (int) VALUE.getVolatile(this);
    }
}
~~~

Đây là thay thế phù hợp cho một nhóm thao tác truy cập/atomic field có ngữ nghĩa tương ứng. Nó **không phải thay thế toàn bộ mọi chức năng của Unsafe**. Nếu mã đang dùng cấp phát bộ nhớ thô, địa chỉ native hoặc thao tác nội bộ khác, cần đánh giá từng chức năng và chọn API được hỗ trợ phù hợp.

## 6. Phân tích JAR và dependency bên ngoài

Một ứng dụng thường phụ thuộc vào nhiều thư viện. Chỉ quét file class của ứng dụng có thể bỏ sót tham chiếu nội bộ nằm trong dependency.

Dùng `--class-path` để đưa các thư viện cần phân tích vào class path:

~~~shell
jdeps --jdk-internals --class-path "lib/*" build/libs/application.jar
~~~

Trong ví dụ này:

- `build/libs/application.jar` là artifact ứng dụng.
- `lib/*` là các JAR dependency được đưa vào class path.
- `--jdk-internals` yêu cầu tìm tham chiếu tới API nội bộ trong các lớp được phân tích.

Trên Windows, dấu phân cách nhiều mục class path là dấu chấm phẩy (`;`). Khi dùng wildcard như `lib/*`, đặt đường dẫn trong dấu nháy kép để shell không xử lý wildcard theo cách khác.

Nếu cần phân tích dependency theo hướng đệ quy, có thể dùng `--recursive`:

~~~shell
jdeps --jdk-internals --recursive --class-path "lib/*" build/libs/application.jar
~~~

Tập lớp được phân tích phụ thuộc vào các đường dẫn và tùy chọn đã truyền. Hãy đưa đúng runtime dependencies vào lệnh; `jdeps` không thể tìm một thư viện nằm ngoài những đầu vào và đường dẫn phân tích được cung cấp.

### 6.1. Quét thư mục build

Nếu build tạo class files trong một thư mục:

~~~shell
jdeps --jdk-internals build/classes/java/main
~~~

Với Maven, thư mục class thường là:

~~~shell
jdeps --jdk-internals target/classes
~~~

Với Gradle, thư mục class thường là:

~~~shell
jdeps --jdk-internals build/classes/java/main
~~~

Đường dẫn thực tế phụ thuộc cấu hình build. Nếu có nhiều source set, module hoặc output directory, hãy quét từng artifact liên quan.

### 6.2. JAR đa phiên bản (multi-release JAR)

Một multi-release JAR có thể chứa các phiên bản class khác nhau trong những thư mục như `META-INF/versions/17`. Khi phân tích loại JAR này, chỉ định release cần kiểm tra:

~~~shell
jdeps --jdk-internals --multi-release 17 app-mr.jar
~~~

`--multi-release` nhận một số nguyên từ 9 trở lên hoặc giá trị `base`. Chọn đúng phiên bản mục tiêu giúp `jdeps` phân tích phần bytecode được dùng cho runtime tương ứng thay vì chỉ dựa trên nội dung nền của JAR.

## 7. Ứng dụng modular và module path

Ứng dụng Java 17 có thể được đóng gói thành named modules. Khi phân tích, cần cung cấp đúng module path và module gốc.

Ví dụ dạng lệnh:

~~~shell
jdeps --jdk-internals --module-path "mods;lib" --module com.example.app
~~~

Trong đó `com.example.app` là tên module của ứng dụng; `mods` và `lib` là vị trí chứa module hoặc dependency tương ứng. Điều chỉnh dấu phân cách path theo hệ điều hành.

Nếu đang phân tích một JAR trên class path, dùng `--class-path` thay vì giả định nó là named module. Hãy chọn đúng mô hình đóng gói của artifact.

Một ứng dụng modular có thể khai báo `requires` tới module chứa package nội bộ, nhưng việc module được đọc không đồng nghĩa mọi package của module đó đều được export. Module readability và package accessibility là hai điều kiện khác nhau.

## 8. jdeps phát hiện gì và không phát hiện gì?

`jdeps` là **static analysis tool**. Nó phân tích những tham chiếu dependency có thể nhận ra từ bytecode. Điều này rất hữu ích, nhưng không thể xem kết quả là danh sách đầy đủ mọi cách ứng dụng có thể chạm tới JDK internals.

### 8.1. Những phụ thuộc thường được phát hiện

- Bytecode có tham chiếu kiểu tới lớp nội bộ.
- Chữ ký field hoặc method có kiểu nội bộ.
- Lớp ứng dụng gọi hoặc sử dụng một API nội bộ theo cách tạo dependency trong class file.
- Lớp trong thư viện dependency có tham chiếu trực tiếp tới JDK internal API, nếu dependency đó nằm trong phạm vi được phân tích.

### 8.2. Những trường hợp có thể bị bỏ sót

`jdeps` không chạy ứng dụng để quan sát mọi đường thực thi. Vì vậy, có thể bỏ sót:

- Reflection truy cập lớp hoặc member bằng tên chuỗi.
- `Class.forName` với tên lớp được tạo động.
- Class loading tùy biến hoặc tên lớp được lấy từ cấu hình bên ngoài.
- Native code/JNI gọi vào thành phần JDK.
- Phụ thuộc được nạp động hoặc service provider không nằm trong phạm vi class files mà lệnh phân tích.
- Hành vi chỉ xuất hiện ở một nhánh runtime hiếm gặp.

Ví dụ, đoạn mã:

~~~java
Class<?> type = Class.forName(configuredClassName);
~~~

không nhất thiết tạo ra một tham chiếu bytecode trực tiếp tới lớp mà chuỗi cấu hình sẽ chỉ định. Nếu giá trị cấu hình trỏ tới một lớp nội bộ, `jdeps` có thể không nhận ra phụ thuộc đó.

Vì thế, kết quả không có cảnh báo chỉ có nghĩa **không phát hiện được tham chiếu nội bộ trong phạm vi phân tích**, không phải bằng chứng tuyệt đối rằng ứng dụng không dùng bất kỳ internal API nào.

### 8.3. Kết hợp các nguồn kiểm tra

Để có độ tin cậy tốt hơn:

1. Quét các class files và JAR của ứng dụng bằng `jdeps`.
2. Quét các thư viện bên thứ ba nằm trong runtime class path/module path.
3. Kiểm tra cấu hình reflection, service loading và native integration.
4. Chạy integration test trên JDK 17 với cấu hình module mặc định.
5. Kiểm tra log cảnh báo và lỗi truy cập trong runtime.
6. Xem xét dependency tree để xác định thư viện nào đưa internal API vào ứng dụng.

## 9. Vì sao jdeps và runtime có thể cho kết quả khác nhau?

Có ba khái niệm khác nhau:

| Công cụ/cơ chế | Câu hỏi được trả lời |
| --- | --- |
| `jdeps --jdk-internals` | Bytecode trong phạm vi phân tích có tham chiếu class-level tới API nội bộ nào? |
| Module system/runtime | Module và package có được phép truy cập trong cấu hình đang chạy không? |
| Integration test | Những luồng thực tế của ứng dụng có hoạt động đúng trên runtime mục tiêu không? |

Một internal API có thể được `jdeps` báo cáo nhưng vẫn truy cập được trong JDK 17 vì package đó thuộc nhóm ngoại lệ được export. Ngược lại, ứng dụng có thể gặp `InaccessibleObjectException` do reflection vào member không mở, dù `jdeps` không báo tham chiếu trực tiếp.

Không nên dùng kết quả của một công cụ để thay thế hoàn toàn hai loại kiểm tra còn lại.

## 10. Phân biệt --add-exports và --add-opens

Trong một số trường hợp chuyển đổi hệ thống cũ, ứng dụng có thể cần quyền truy cập tạm thời trong lúc chờ thay thế dependency. Module system cung cấp hai tùy chọn có phạm vi khác nhau:

| Tùy chọn | Mục đích | Thời điểm thường dùng |
| --- | --- | --- |
| `--add-exports module/package=target` | Export package cụ thể để mã ở module đích truy cập các kiểu public trong package đó. | Khi mã cần truy cập kiểu public trong package vốn không export. |
| `--add-opens module/package=target` | Mở package cho deep reflection vào member không public. | Khi thư viện reflection cần truy cập field/method/constructor không public. |

Ví dụ về hình thức cú pháp:

~~~shell
java --add-exports java.base/some.internal.package=ALL-UNNAMED -jar app.jar
java --add-opens java.base/some.internal.package=ALL-UNNAMED -jar app.jar
~~~

`some.internal.package` chỉ là tên minh họa; phải thay bằng package và module thực tế. Không sao chép lệnh này khi chưa xác định đúng nguyên nhân truy cập.

Hai tùy chọn trên là cơ chế cấp quyền truy cập có chủ đích, **không biến API nội bộ thành API được hỗ trợ**. Chúng cũng không làm cho `jdeps` ngừng báo cáo dependency. Hãy dùng quyền mở/export hẹp trong giai đoạn chuyển đổi và ưu tiên loại bỏ phụ thuộc nội bộ khỏi kiến trúc lâu dài.

## 11. Quy trình xử lý kết quả jdeps

Khi công cụ báo một dependency nội bộ, nên xử lý theo từng bước:

### Bước 1: Xác định lớp sở hữu dependency

Đọc dòng báo cáo để biết lớp ứng dụng hay lớp trong thư viện nào tham chiếu API nội bộ. Nếu dependency đến từ thư viện bên thứ ba, ghi nhận artifact và phiên bản thư viện.

### Bước 2: Xác định API và module chứa nó

Tìm package, class và module được báo cáo. Kiểm tra API đó:

- Còn tồn tại trong JDK 17 hay đã bị loại bỏ?
- Có được export hay đang bị đóng gói?
- Có API chuẩn thay thế không?
- Có gợi ý trong tài liệu JDK hoặc JEP liên quan không?

### Bước 3: Chọn hướng thay thế

Ưu tiên API công khai thuộc Java SE hoặc một thư viện bên ngoài có hợp đồng hỗ trợ rõ ràng. Nếu không có thay thế trực tiếp, đánh giá lại cách triển khai thay vì giữ nguyên internal dependency chỉ vì có thể mở package bằng cờ runtime.

### Bước 4: Cập nhật dependency bên thứ ba

Nếu tham chiếu nằm trong thư viện:

- Tìm phiên bản mới đã loại bỏ internal API.
- Kiểm tra release notes của nhà cung cấp.
- Nếu thư viện chưa có bản sửa, đánh giá thư viện thay thế hoặc giới hạn phạm vi sử dụng.
- Không chỉnh sửa bytecode hoặc sao chép lớp nội bộ của JDK vào ứng dụng để né module system.

### Bước 5: Chạy lại phân tích và kiểm thử

Sau khi thay thế:

~~~shell
jdeps --jdk-internals build/libs/application.jar
~~~

Tiếp tục chạy unit test, integration test và smoke test trên JDK 17. Mục tiêu là không còn phụ thuộc nội bộ ngoài những ngoại lệ được chấp nhận có lý do rõ ràng; đồng thời bảo đảm hành vi ứng dụng vẫn đúng.

## 12. Tích hợp vào quy trình build và CI

`jdeps` có thể được đưa vào một bước kiểm tra trước khi đóng gói hoặc phát hành. Ví dụ một script shell:

~~~shell
#!/usr/bin/env sh
set -eu

APP_JAR="build/libs/application.jar"
DEPS_DIR="build/dependencies"

jdeps --jdk-internals \
  --class-path "$DEPS_DIR/*" \
  "$APP_JAR"
~~~

Lệnh trên in kết quả để người phát triển xem xét. Nếu muốn CI thất bại theo tiêu chí nội bộ, có thể viết bước kiểm tra riêng dựa trên output hoặc dùng plugin/build integration phù hợp. Không nên giả định mọi phiên bản `jdeps` đều cung cấp một cờ chung như `--fail-on-internal`; hãy xác định chính sách CI và cách parse output một cách rõ ràng.

Một pipeline thực tế có thể gồm:

~~~text
Compile application and dependencies
                |
                v
        Run jdeps --jdk-internals
                |
                v
       Review reported dependencies
                |
        +-------+-------+
        |               |
      Found           None found
        |               |
        v               v
 Upgrade/replace    Continue tests
        |               |
        v               v
    Re-run jdeps   Integration tests
        |               |
        +-------+-------+
                |
                v
       Package and release
~~~

Nên lưu kết quả phân tích theo từng bản build để dễ phát hiện dependency nội bộ mới được đưa vào qua thay đổi code hoặc nâng phiên bản thư viện.

## 13. Những tùy chọn liên quan

| Tùy chọn | Công dụng |
| --- | --- |
| `--jdk-internals` | Tìm dependency tới JDK internal APIs. |
| `--class-path path` | Khai báo nơi tìm class files và thư viện trên class path. |
| `--module-path path` | Khai báo nơi tìm các module. |
| `--recursive` | Duyệt đệ quy các runtime dependencies. |
| `--multi-release version` | Chọn phiên bản class khi xử lý multi-release JAR. |
| `--include regex` | Giới hạn các lớp đầu vào được phân tích theo biểu thức chính quy. |
| `--version` | In phiên bản công cụ. |
| `--help` | In hướng dẫn sử dụng. |

Một số tổ hợp bị giới hạn. Cụ thể, tài liệu Java 17 quy định `--jdk-internals` không dùng cùng `-p`, `-e` hoặc `-s`. Khi cần lọc, hãy kiểm tra cú pháp và giới hạn của đúng phiên bản JDK đang dùng.

## 14. Những lỗi thường gặp

| Lỗi | Vì sao không hiệu quả | Cách xử lý |
| --- | --- | --- |
| Chạy `jdeps` trên file `.java` | Công cụ phân tích class files đã biên dịch. | Biên dịch trước, rồi quét thư mục output hoặc JAR. |
| Chỉ quét JAR ứng dụng | Dependency bên thứ ba có thể chứa internal API. | Cung cấp class path/module path và quét thư viện runtime. |
| Dùng JDK khác với phiên bản mục tiêu | Danh sách module/API có thể khác. | Dùng `jdeps` từ JDK 17 hoặc chỉ định system image phù hợp. |
| Nghĩ không có output nghĩa là đã chứng minh không có internal API | Phân tích tĩnh không nhận diện mọi reflection/dynamic loading. | Kiểm tra cấu hình, runtime test và dependency tree. |
| Nghĩ mọi package `sun.*` đều giống nhau | Một số package ngoại lệ được export; một số package nội bộ khác bị đóng. | Dựa trên kết quả phân tích và tài liệu module. |
| Thấy `sun.misc.Unsafe` còn truy cập được nên xem là API ổn định | Đây là ngoại lệ nội bộ, không có cam kết như API Java SE. | Đánh giá thay thế chuẩn cho từng thao tác. |
| Dùng `--add-opens` để sửa mọi lỗi module | Tùy chọn này dành cho deep reflection, không thay thế mọi vấn đề export/type access. | Phân biệt đúng `--add-exports` và `--add-opens`. |
| Coi gợi ý replacement là bản sửa tự động | Gợi ý có thể chỉ là tài liệu/JEP và không tương đương hoàn toàn. | Xác minh ngữ nghĩa và kiểm thử sau migration. |
| Dùng quyền mở package rộng như giải pháp dài hạn | Tăng phụ thuộc vào chi tiết nội bộ và giảm tính đóng gói. | Giới hạn quyền tạm thời rồi loại bỏ dependency. |
| Chỉ chạy jdeps một lần trước khi phát hành | Dependency mới có thể được thêm ở lần build sau. | Tích hợp quét vào quy trình CI định kỳ. |

## 15. Ví dụ quy trình trên một JAR

Giả sử ứng dụng đã được đóng gói:

~~~text
project/
  build/
    libs/
      application.jar
  lib/
    dependency-a.jar
    dependency-b.jar
~~~

Trước hết, xác nhận JDK:

~~~shell
java --version
jdeps --version
~~~

Quét ứng dụng cùng thư viện:

~~~shell
jdeps --jdk-internals \
  --class-path "lib/*" \
  build/libs/application.jar
~~~

Nếu có dependency được báo cáo, ghi lại lớp tham chiếu, package nội bộ và module chứa API đó. Sau đó kiểm tra xem nguồn là mã ứng dụng hay thư viện bên ngoài.

Sau khi cập nhật mã hoặc nâng phiên bản thư viện, build lại và chạy lại đúng lệnh. Một kết quả sạch là tín hiệu tốt cho dependency tĩnh được công cụ nhận diện, nhưng vẫn cần chạy ứng dụng và kiểm thử trên JDK 17 để kiểm tra các truy cập động.

## 16. Câu hỏi thường gặp

**`jdeps --jdk-internals` có phân tích source code không?**  
Không. Nó phân tích bytecode trong file class, thư mục class hoặc JAR. Hãy biên dịch trước khi chạy công cụ.

**`--jdk-internals` có phải tên duy nhất không?**  
Không. Java 17 hỗ trợ cả alias `-jdkinternals`. Tên dài dễ đọc hơn trong script.

**Công cụ có tìm được internal API trong dependency không?**  
Có, nếu các lớp dependency nằm trong đầu vào hoặc class path/module path được cung cấp và thuộc phạm vi phân tích. Hãy khai báo đúng runtime dependencies.

**Không có kết quả có nghĩa ứng dụng chắc chắn không dùng internal API?**  
Không. Reflection, tên lớp tạo động, native code và dependency không nằm trong phạm vi quét có thể không được phát hiện.

**Tại sao `sun.misc.Unsafe` vẫn truy cập được trong Java 17 nhưng vẫn bị cảnh báo?**  
Đây là một ngoại lệ được export qua `jdk.unsupported`. Nó vẫn là API nội bộ và không có cam kết tương thích như API chuẩn.

**`jdeps` có tự sửa dependency không?**  
Không. Nó chỉ báo cáo dependency và có thể đưa gợi ý. Việc thay thế phải do nhóm phát triển thực hiện và kiểm thử.

**Có thể dùng `--add-exports` hoặc `--add-opens` thay cho migration không?**  
Chúng có thể cấp quyền truy cập hẹp để hỗ trợ chuyển đổi trong một số trường hợp, nhưng không biến API nội bộ thành API ổn định. Nên ưu tiên loại bỏ phụ thuộc.

**Có cần chạy `jdeps` mỗi lần build không?**  
Nên tích hợp vào CI hoặc các mốc kiểm tra dependency quan trọng để phát hiện phụ thuộc mới trước khi phát hành.

## 17. Tài liệu tham khảo chính thức

- [The jdeps Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): cú pháp, `--jdk-internals`, class path, module path, multi-release JAR và các giới hạn tổ hợp tùy chọn.
- [Preparing for Migration — Oracle JDK 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): hướng dẫn chạy `jdeps` trên ứng dụng và lưu ý giới hạn của phân tích tĩnh.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): lý do và phạm vi đóng gói mạnh các thành phần nội bộ của JDK.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): cơ chế module, export package và quyền truy cập giữa các module.
- [Java SE 17 API — java.lang.invoke.VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): API chuẩn cho truy cập biến và các thao tác nguyên tử có ngữ nghĩa bộ nhớ xác định.
- [Java SE 17 API — Module jdk.jdeps](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdeps/module-summary.html): module chứa các công cụ phân tích dependency như `jdeps`.

**Nguyên tắc áp dụng:** Chạy `jdeps --jdk-internals` trên bytecode của ứng dụng và các dependency liên quan để tìm tham chiếu tới JDK internal APIs. Đọc kết quả theo lớp, package và module; thay thế bằng API công khai phù hợp; sau đó chạy lại phân tích và kiểm thử trên Java 17. Hãy xem `jdeps` là một công cụ phát hiện dependency tĩnh quan trọng, không phải bằng chứng duy nhất về khả năng tương thích runtime.
