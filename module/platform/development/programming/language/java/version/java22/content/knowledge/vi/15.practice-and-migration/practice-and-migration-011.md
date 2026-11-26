# Rà soát tương thích, cấu hình native access và tài liệu triển khai trước khi sử dụng thực tế

## Phạm vi bài học

Bài thuộc chương **Vận dụng và nâng cấp** của module **JAVA_VERSION_JAVA22**, tập trung vào việc đưa những kiến thức xuất hiện trong Java 22 và còn hữu ích ở Java hiện đại vào môi trường vận hành thực tế.

Một chương trình biên dịch được trên máy phát triển chưa chứng minh rằng nó dùng đúng runtime, tải được thư viện native hoặc có thể quay về phiên bản trước khi triển khai gặp lỗi. Trước khi phát hành, cần xác định chính xác tổ hợp được hỗ trợ và lưu được bằng chứng kiểm tra cho tổ hợp đó.

Bài sử dụng API FFM chính thức trong `java.lang.foreign`, không hướng dẫn dùng lại các bản FFM preview hoặc incubator cũ. Các ví dụ riêng cho runtime hiện đại được đối chiếu với tài liệu **JDK 27 tại ngày 25/11/2026**. JDK 27 là mốc tài liệu của bài, không phải yêu cầu buộc mọi hệ thống phải chọn phiên bản này.

Bạn cần hoàn thành ba kết quả:

1. Một hồ sơ tương thích xác định JDK, dependency, hệ điều hành, kiến trúc và thư viện native.
2. Một cấu hình khởi động cấp native access đúng nơi thực sự sử dụng.
3. Một tài liệu triển khai giúp người vận hành khởi động, xác minh, dừng và khôi phục ứng dụng.

Các quy trình trong bài là hướng dẫn thực hành; những trạng thái đạt hay chưa đạt của hệ thống cụ thể phải được điền từ kết quả chạy thật.

## 1. Xác định đối tượng cần tương thích

Từ “hỗ trợ Java 22 trở lên” có thể che giấu nhiều giả định. Hãy tách riêng các chiều sau:

| Chiều tương thích | Cần ghi rõ | Ví dụ về vấn đề có thể gặp |
| --- | --- | --- |
| Mã nguồn | Mức ngôn ngữ và API được dùng | Mã gọi API chỉ được chuẩn hóa ở phiên bản mới hơn baseline. |
| Bytecode | Target khi biên dịch và JDK chạy | Runtime không đọc được class file mới hơn nó. |
| Dependency Java | Phiên bản framework, driver, agent, thư viện | Agent đọc bytecode chưa hỗ trợ định dạng class của JDK đích. |
| Trạng thái tính năng | Chính thức, preview hay incubator | Bật một cờ không làm API preview cũ trở thành API hiện tại. |
| Native | Binary, chữ ký hàm, ABI và thư viện phụ thuộc | Đúng tên tệp nhưng sai kiến trúc hoặc thiếu dependency của hệ điều hành. |
| Cấu hình chạy | Module path, classpath và JVM options | Cờ chỉ có trong IDE, còn tiến trình dịch vụ không nhận được. |
| Hành vi | Kết quả, định dạng, timeout, xử lý lỗi | Chương trình khởi động nhưng đầu ra hoặc hành vi lỗi thay đổi. |
| Tài nguyên | Heap, bộ nhớ native, thread và CPU | Heap ổn định trong khi vùng nhớ ngoài heap tăng theo yêu cầu. |

Đơn vị để xác nhận triển khai là một tổ hợp cụ thể, chẳng hạn:

```text
Artifact Java + bộ dependency
+ bản phân phối và build JDK
+ hệ điều hành / kiến trúc / runtime C
+ bộ binary native
+ cấu hình khởi động
```

Thay một thành phần của tổ hợp có thể làm bằng chứng trước đó không còn đầy đủ. Vì vậy, hồ sơ phát hành cần gắn với phiên bản artifact và cấu hình, không chỉ gắn với tên nhánh mã nguồn.

### 1.1. Ghi baseline và runtime đích thành hai mục

- **Baseline biên dịch:** mức Java tối thiểu mà mã nguồn và API của sản phẩm cần đáp ứng.
- **Runtime triển khai:** JDK thực sự chạy trong dịch vụ hoặc image phát hành.

Ví dụ, một thành phần chỉ dùng FFM chính thức có thể đặt baseline Java 22 trong khi được kiểm tra trên runtime mới hơn. Nếu thêm API chính thức từ Java 24 hoặc 25, phải xem lại baseline.

Không nâng baseline chỉ vì máy phát triển được cài JDK mới. Ngược lại, không tuyên bố còn hỗ trợ baseline cũ sau khi đã thêm API mới mà không có phương án tương thích được kiểm tra.

## 2. Rà soát trạng thái tính năng trước khi chốt target

Phân biệt ba nhóm sau:

| Nhóm | Ý nghĩa khi triển khai | Việc cần làm |
| --- | --- | --- |
| Tính năng hoặc API chính thức | Không cần cờ preview chỉ để sử dụng tính năng đó | Kiểm tra phiên bản xuất hiện, chữ ký và dependency thực tế. |
| Preview | Gắn với một release cụ thể, có thể thay đổi trước khi chuẩn hóa | Dùng đúng tài liệu của JDK đích; đánh giá lại mã nguồn khi nâng JDK. |
| Incubator | Module thử nghiệm có vòng đời riêng | Xác minh module, API và cách kích hoạt trên từng JDK được hỗ trợ. |

Một số ví dụ giúp đọc đúng tài liệu Java 22 trong bối cảnh hiện đại:

- FFM đã chính thức từ Java 22; việc gọi các phương thức restricted vẫn liên quan tới native access. “Chính thức” và “được cấp native access” là hai thuộc tính khác nhau.
- `Gatherer` có API chính thức từ Java 24. Khi tiếp tục phát triển mã từng học dưới dạng preview, đối chiếu [Gatherer hiện hành](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html).
- Class-File API có package chính thức từ Java 24; xem [java.lang.classfile](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html).
- `ScopedValue` có API chính thức từ Java 25; xem [ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html).
- Vector API vẫn là module incubator trong tài liệu JDK 27. Nếu sử dụng, cần kiểm tra riêng `jdk.incubator.vector`, thay vì coi nó có cùng trạng thái với FFM. Xem [module Vector API của JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

Các mốc trên dùng để quyết định baseline và đọc đúng API. Bài không yêu cầu giữ lại một biến thể preview cũ để triển khai mới.

### 2.1. Không chuyển nguyên bytecode preview cũ sang JDK mới

Bật `--enable-preview` trên JDK mới không cho phép chạy mọi class file preview của các release trước. JVM quy định class file phụ thuộc preview chỉ được nạp bởi đúng release tương ứng, với preview được bật. Xem [JVMS: phiên bản class file và preview](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.1).

Khi nâng JDK cho ứng dụng từng dùng preview:

1. Xác định các phần đang phụ thuộc preview.
2. Chuyển mã sang API hoặc cú pháp được JDK đích hỗ trợ.
3. Biên dịch lại ứng dụng và các thành phần liên quan.
4. Kiểm tra lại hành vi, đặc biệt khi chữ ký hoặc hợp đồng API đã thay đổi.
5. Bỏ cờ preview nếu ứng dụng sau chuyển đổi không còn cần nó.

Không để cờ tồn tại trong cấu hình triển khai chỉ vì một bài thực hành trước đây từng sử dụng.

## 3. Kiểm kê toolchain và dependency

### 3.1. Nhận diện đúng các tiến trình Java

Ghi phiên bản compiler và launcher dùng trong pipeline:

```text
java --version
javac --version
```

Ngoài phiên bản chính, hồ sơ nên có nhà cung cấp, build đầy đủ và nơi lấy runtime. Sau đó xác nhận các tiến trình thực tế:

| Tiến trình | Thông tin cần xác nhận |
| --- | --- |
| Compiler trong CI | JDK và target biên dịch. |
| JVM chạy kiểm thử | JDK cùng các cờ cần cho bài kiểm tra. |
| JVM chạy công cụ build | JDK có được công cụ hỗ trợ hay không. |
| Tiến trình ứng dụng khi triển khai | Runtime và cấu hình launcher thực tế. |

Các tiến trình này có thể khác nhau. Một cờ đặt cho tiến trình build không tự trở thành cờ của JVM chạy ứng dụng hoặc JVM chạy kiểm thử riêng.

Hướng dẫn di chuyển của Oracle cũng yêu cầu xem lại công cụ, thư viện và hành vi chương trình khi thay JDK. Xem [Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html).

### 3.2. Sử dụng --release đúng mục đích

Với mã chỉ dùng các tính năng và API chính thức có trong Java 22, ví dụ:

```text
javac --release 22 -d out src/com/example/report/Main.java
```

`--release` kiểm soát mức ngôn ngữ, target class file và API nền tảng được compiler cung cấp cho release đó, trong phạm vi các release compiler hỗ trợ. Nó không chứng nhận dependency bên thứ ba hay binary C tương thích.

Nếu mã sử dụng `Gatherer` chính thức từ 24, đặt `--release 22` không biến API đó thành API của 22. Với API incubator, cũng phải đánh giá theo JDK và module thực sự được dùng.

Xem [javac: biên dịch cho release khác](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

### 3.3. Phân tích phụ thuộc vào JDK và API deprecated

Các tên tệp dưới đây là minh họa; khi áp dụng, cung cấp đầy đủ dependency của artifact thực tế.

```text
jdeps --multi-release 27 --recursive --jdk-internals --class-path "lib/native-bridge.jar" report-app.jar
```

Lệnh tập trung vào phụ thuộc JDK internal. `--multi-release 27` chọn nhánh tương ứng khi phân tích multi-release JAR; đây không phải cờ chuyển đổi bytecode.

```text
jdeprscan --for-removal --class-path "lib/native-bridge.jar" report-app.jar
```

Lệnh thứ hai tìm việc sử dụng API Java SE đã được đánh dấu deprecated để loại bỏ. `jdeprscan` không thay thế công cụ rà soát deprecated API của thư viện bên thứ ba.

Nếu thiếu class phụ thuộc, bổ sung classpath rồi xem lại kết quả. Không kết luận “không có vấn đề” từ một lần quét còn báo lỗi phân giải dependency.

Tham khảo [jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) và [jdeprscan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html).

### 3.4. Tìm các thành phần dùng native trên JDK hiện đại

Trên JDK 27 có công cụ `jnativescan`:

```text
jnativescan --release 27 --module-path modules --add-modules com.example.report
```

Để nhận danh sách module cần xem xét:

```text
jnativescan --release 27 --module-path modules --add-modules com.example.report --print-native-access
```

Ví dụ cho một JAR trên classpath:

```text
jnativescan --release 27 --class-path report-app.jar --print-native-access
```

Công cụ tìm tham chiếu tới phương thức restricted và khai báo phương thức `native`. Target release nên khớp runtime dự định dùng. Các lệnh này thuộc bộ công cụ JDK hiện đại đang xét, không phải yêu cầu công cụ sẵn có trong JDK 22. Xem [jnativescan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jnativescan.html).

Kết quả là đầu vào cho việc rà soát, không phải danh sách để tự động cấp quyền mà bỏ qua kiểm tra. Với plugin, reflection, classloader riêng hoặc gói có JAR lồng nhau, phải bảo đảm phạm vi phân tích phản ánh đúng cách chạy.

Phân tích tĩnh và chạy thử bổ sung cho nhau: công cụ chỉ thấy những gì nó phân tích được, còn bài kiểm tra chỉ đi qua những nhánh thực sự đã chạy.

## 4. Hiểu chính xác native access

### 4.1. Native access áp dụng cho thao tác nào?

Trong FFM, các thao tác như tải thư viện bằng `SymbolLookup.libraryLookup`, tạo downcall, tạo upcall hoặc diễn giải lại kích thước vùng nhớ có thể thuộc nhóm restricted.

Việc cấp phát và đọc/ghi một segment theo các API thông thường không đồng nghĩa mọi thao tác đều yêu cầu native access. Cần đối chiếu phương thức cụ thể, thay vì cấp quyền chỉ vì thấy một import `java.lang.foreign`. Xem [danh sách phương thức restricted của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/restricted-list.html).

Trên JDK hiện đại, cũng phải kiểm kê dependency dùng JNI. Từ JDK 24, cơ chế cảnh báo và hạn chế được điều chỉnh để áp dụng nhất quán hơn giữa JNI và FFM. Một thư viện dùng JNI gián tiếp vẫn có thể làm ứng dụng cần cấu hình native access. Xem [thay đổi native access từ JDK 24](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-24.html).

### 4.2. Cấp cho module thực hiện thao tác

Giả sử cấu trúc ứng dụng là:

```text
com.example.report
        |
        v
com.example.nativebridge
        |
        v
FFM restricted methods
        |
        v
libcodec.so / codec.dll / libcodec.dylib
```

Nếu mã trong `com.example.nativebridge` trực tiếp thực hiện các lời gọi restricted, module đó cần được cấp native access. Chỉ cấp cho module chứa `main` không tự cấp cho dependency.

Với JNI, cần xác định cả nơi tải thư viện và nơi khai báo các phương thức native; không chỉ nhìn nơi gọi API cấp cao của thư viện.

Các phần bên dưới dùng `com.example.report` và `com.example.nativebridge` làm tên module minh họa.

### 4.3. Các cờ giải quyết những vấn đề khác nhau

| Cấu hình | Mục đích |
| --- | --- |
| `--enable-native-access=...` | Cho phép module được chỉ định thực hiện native access. |
| `--enable-preview` | Cho phép dùng preview của đúng release theo quy tắc tương ứng. |
| `--add-modules=...` | Bổ sung module vào tập module gốc được resolve. |
| `--add-opens=...` | Mở package cho deep reflection theo phạm vi đã chỉ định. |
| `-Djava.library.path=...` | Cung cấp một đường tìm kiếm thư viện cho các cơ chế tải dùng thuộc tính này. |

Không thay thế một cờ bằng cờ khác. FFM chính thức không cần `--enable-preview` chỉ vì có lời gọi native. Thêm `java.library.path` cũng không cấp quyền native access.

Một đường dẫn đúng chưa chứng minh thư viện tải được: binary còn phải phù hợp với hệ điều hành, kiến trúc và các dependency native.

## 5. Cấu hình launcher cho classpath và module path

### 5.1. Ứng dụng chạy trên classpath

Ví dụ JAR thực thi có manifest và dependency phù hợp:

```text
java --enable-native-access=ALL-UNNAMED -jar report-app.jar
```

`ALL-UNNAMED` áp dụng cho code trên classpath, không chọn riêng một JAR trong số đó. Cần ghi rõ phạm vi này trong tài liệu triển khai.

Cờ của JVM nằm trước `-jar`, tên lớp chính hoặc `--module`. Nếu đặt sau tên JAR, chuỗi đó trở thành đối số ứng dụng thay vì được launcher xử lý như JVM option.

### 5.2. Ứng dụng chạy theo module

Giả sử thư mục `modules` chứa các module của ứng dụng:

```text
java --enable-native-access=com.example.nativebridge --module-path modules --module com.example.report/com.example.report.Main
```

Nếu có nhiều module trực tiếp sử dụng native:

```text
--enable-native-access=com.example.nativebridge,com.vendor.codec
```

Không dùng tên package, tên tệp DLL hoặc tên artifact Maven thay cho tên module.

Kiểm tra tên module từ JAR:

```text
jar --describe-module --file modules/native-bridge.jar
```

JAR đặt trên module path có thể là explicit module hoặc automatic module; tên cần lấy từ kết quả và cách đóng gói thực tế. Xem [jar --describe-module](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html).

Một JAR có `module-info.class` nhưng được đặt trên classpath hoạt động như JAR không modular. Vì vậy, tên module trên bản đóng gói không đủ để kết luận module runtime. Xem [JAR File Specification: Modular JAR files](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html#modular-jar-files).

### 5.3. Manifest của executable JAR

Một JAR chạy bằng `java -jar` có thể dùng thuộc tính:

```text
Enable-Native-Access: ALL-UNNAMED
```

Giá trị được hỗ trợ ở đây là `ALL-UNNAMED`; thuộc tính này không nhận một danh sách tên module tùy ý. Không xem manifest của một JAR thư viện bất kỳ trên classpath là cơ chế tự cấp quyền cho chính thư viện.

Tham khảo [JAR manifest: Enable-Native-Access](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html#main-attributes).

Lựa chọn cấu hình qua manifest hay launcher cần được ghi rõ. Khi rà soát sự cố, xem cả hai nguồn thay vì chỉ đọc một script.

### 5.4. Không phát tán cờ vào môi trường dùng chung

Có thể truyền tùy chọn qua `JDK_JAVA_OPTIONS`, nhưng biến môi trường này được launcher `java` đọc và có thể được các tiến trình con kế thừa. Nếu sử dụng, giới hạn nó trong cấu hình của dịch vụ và ghi giá trị trong hồ sơ triển khai.

Giữ một nơi quản lý chính cho cấu hình khởi động giúp tránh trường hợp:

- IDE cấp quyền, còn dịch vụ không cấp.
- Máy CI có biến môi trường làm bài kiểm tra thành công ngoài dự kiến.
- Script mới đã sửa nhưng service wrapper vẫn dùng cấu hình cũ.

Cú pháp và cách launcher xử lý đối số được quy định trong [java command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

## 6. Xác minh chính sách native access trên runtime đích

### 6.1. Không coi cảnh báo là bằng chứng đã cấu hình đúng

Theo tài liệu JDK 27 tại mốc đối chiếu của bài:

| Chế độ | Hành vi khi module chưa được cấp native access |
| --- | --- |
| `warn` | Cho phép thao tác và phát cảnh báo theo cơ chế của runtime; đây vẫn là mặc định được tài liệu JDK 27 mô tả. |
| `deny` | Từ chối thao tác native access không được cấp, bằng `IllegalCallerException`. |

Bài dùng `deny` như một cách kiểm tra cấu hình tường minh. Không dùng việc tắt cảnh báo làm tiêu chí sẵn sàng triển khai. Xem [Restricted Methods của JDK 27](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html).

Với runtime JDK 27, một lệnh kiểm tra module hóa là:

```text
java --illegal-native-access=deny --enable-native-access=com.example.nativebridge --module-path modules --module com.example.report/com.example.report.Main
```

Với classpath:

```text
java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED -jar report-app.jar
```

`--illegal-native-access` có từ JDK 24, không phải tùy chọn cho JDK 22. Nếu sản phẩm hỗ trợ cả baseline cũ và runtime mới, cấu hình launcher phải theo đúng phiên bản chạy. Không thêm tùy chọn JDK mới vào mọi profile rồi chấp nhận lỗi “unrecognized option”.

Khi JDK thay đổi, kiểm tra lại sự tồn tại và mặc định của tùy chọn. Hồ sơ phát hành cần lưu chính sách đã dùng, không dựa vào một suy đoán về release tương lai.

### 6.2. Đi qua đường native thật

Một ứng dụng có thể chỉ tải thư viện ở yêu cầu đầu tiên. Khi đó, khởi động thành công với `deny` chưa chứng minh đã cấu hình đúng.

Bài kiểm tra cần kích hoạt có chủ đích:

1. Tải thư viện cần dùng.
2. Tìm các symbol bắt buộc.
3. Tạo binding theo đúng chữ ký.
4. Gọi một thao tác nhỏ có đầu vào và kết quả biết trước.
5. Đi qua đường lỗi hoặc giải phóng tài nguyên liên quan.

Nếu có plugin hoặc tính năng native tùy chọn, xác định rõ những nhánh nào được phép bật trong cấu hình phát hành và kiểm tra các nhánh đó.

Không để một fallback tự động che mất lỗi. Nếu hệ thống được phép chuyển sang Java, quan sát và ghi nhận chế độ đang chạy; nếu native là bắt buộc, readiness phải phản ánh việc chưa sẵn sàng.

### 6.3. Kiểm tra quyền ở nơi chứa bridge

`Module.isNativeAccessEnabled()` có từ Java 22. Có thể dùng một kiểm tra khởi động trong chính thành phần làm bridge:

```java
package com.example.nativebridge;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class NativeBootstrap {
    private NativeBootstrap() {}

    public static Path checkedLibraryPath(String configuredPath)
            throws IOException {
        Module module = NativeBootstrap.class.getModule();

        if (!module.isNativeAccessEnabled()) {
            String target = module.isNamed()
                    ? module.getName()
                    : "ALL-UNNAMED";

            throw new IllegalStateException(
                    "Native access is required; start with "
                    + "--enable-native-access=" + target);
        }

        Path path = Path.of(configuredPath);
        if (!path.isAbsolute()) {
            throw new IllegalArgumentException(
                    "Native library path must be absolute");
        }

        Path realPath = path.toRealPath();
        if (!Files.isRegularFile(realPath)) {
            throw new IllegalArgumentException(
                    "Native library path is not a regular file");
        }
        return realPath;
    }
}
```

Đây là chính sách kiểm tra sớm của ứng dụng, không phải mã tải thư viện hoàn chỉnh. Phương thức chủ động báo thiếu quyền kể cả khi runtime hiện tại còn cho phép chạy kèm cảnh báo.

Lấy module của lớp bridge giúp kiểm tra đúng nơi dự định gọi restricted methods. Việc module có quyền và đường dẫn tồn tại chưa xác minh ABI, dependency native hoặc chữ ký hàm. Các bước đó vẫn cần được thực hiện sau đó. Xem [Module.isNativeAccessEnabled](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/Module.html#isNativeAccessEnabled()).

## 7. Rà soát binary native và vòng đời bộ nhớ

### 7.1. Hồ sơ tương thích native

Lưu tối thiểu các thông tin sau cho mỗi binary được đóng gói:

| Mục | Nội dung cần xác nhận |
| --- | --- |
| Định danh binary | Tên, phiên bản, nguồn build và checksum. |
| Nền tảng | Hệ điều hành, kiến trúc, runtime C và các yêu cầu hệ thống liên quan. |
| Dependency native | Những thư viện phụ thuộc cần có trong môi trường chạy. |
| ABI | Calling convention, kiểu C, cách biểu diễn struct, padding và alignment. |
| Symbol | Tên hàm xuất ra và quy tắc phiên bản của thư viện. |
| Chữ ký Java | FunctionDescriptor và kiểu MethodHandle tương ứng. |
| Hợp đồng lỗi | Mã trả về, output parameter hoặc cơ chế lỗi khác theo tài liệu thư viện. |

Linker dùng ABI để tạo lời gọi. Các kiểu như C `long` hoặc `size_t` không nên được ánh xạ bằng một giả định chung cho mọi nền tảng. `Linker.canonicalLayouts()` cung cấp các layout chuẩn theo ABI. Xem [Linker](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html).

Tên symbol đúng không chứng minh descriptor đúng. Không chờ một lời gọi tình cờ thành công rồi xem đó là xác nhận chữ ký.

### 7.2. Ghi rõ quyền sở hữu và thời gian sống

Với mỗi con trỏ đi qua biên Java/native, trả lời:

- Ai cấp phát và ai giải phóng?
- Kích thước vùng nhớ được xác định từ đâu?
- Native chỉ dùng con trỏ trong lời gọi hay giữ lại?
- Những thread nào được phép truy cập?
- Khi dừng dịch vụ, điều gì bảo đảm native đã ngừng sử dụng?

`Arena.ofConfined()` dành cho truy cập theo thread sở hữu. `Arena.ofShared()` cho phép nhiều thread truy cập, nhưng việc chia sẻ arena không tự tạo quy tắc đồng bộ cho dữ liệu của ứng dụng. Xem [Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html).

Nếu có callback, cần dừng hoặc hủy đăng ký callback theo hợp đồng thư viện, đợi native ngừng gọi rồi mới giải phóng stub và các vùng nhớ liên quan.

Đối với thư viện được tải bằng `SymbolLookup.libraryLookup(..., arena)`, arena còn liên quan tới vòng đời lookup và thư viện. Phạm vi này phải bao trùm các lời gọi sử dụng symbol. Xem [SymbolLookup](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SymbolLookup.html).

### 7.3. Theo dõi bộ nhớ ngoài heap

FFM có thể dùng vùng nhớ ngoài heap. Vì vậy, một phép đo heap đơn lẻ không đủ để đánh giá tổng tài nguyên tiến trình. Xem [MemorySegment: heap và native segments](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html).

Khi kiểm tra tải lặp lại, quan sát:

- Bộ nhớ toàn tiến trình và xu hướng sau nhiều vòng xử lý.
- Số công việc native đang chạy và kích thước buffer tương ứng.
- Việc giải phóng khi lời gọi thành công, báo lỗi hoặc bị hủy.
- Thời gian dừng và tình trạng công việc chưa hoàn tất.

Chỉ đặt giới hạn và chỉ tiêu dựa trên những gì đã được đo trong cấu hình đích. Ví dụ một ứng dụng native phải dự trù thêm buffer và thư viện bên cạnh phần heap đã cấu hình.

## 8. Kiểm tra artifact triển khai trong môi trường đại diện

Không dừng ở bài kiểm tra chạy từ IDE. Dùng chính JAR, bộ module hoặc runtime image sẽ được phát hành.

### 8.1. Ma trận kiểm tra cần có mục đích

| Nhóm | Nội dung kiểm tra | Bằng chứng cần lưu |
| --- | --- | --- |
| Khởi động | Đúng runtime, đúng options, đủ dependency | Log nhận diện bản build và cấu hình đã chọn. |
| Nghiệp vụ | Đầu vào đại diện, biên, dữ liệu lỗi | Kết quả và tiêu chí đối chiếu. |
| Native access | Đi qua nhánh native thật với quyền tường minh | Module cần quyền và kết quả khi áp dụng chính sách đã chọn. |
| ABI và thư viện | Load, tìm symbol, gọi hàm đã biết | Binary đã dùng và kết quả phép gọi. |
| Vòng đời | Thành công, lỗi, timeout, hủy và shutdown | Trình tự dọn tài nguyên và công việc còn tồn. |
| Hiệu năng | Throughput, độ trễ và tài nguyên theo tải | Điều kiện đo, mức tải và tiêu chí chấp nhận. |
| Triển khai | Chạy bằng launcher hoặc service wrapper thật | Lệnh hoặc cấu hình dịch vụ có phiên bản. |
| Khôi phục | Quay lại bộ artifact đã xác định | Kết quả khôi phục và giới hạn về dữ liệu. |

Không nhân toàn bộ các tổ hợp theo thói quen. Xác định môi trường thực sự được hỗ trợ, chọn kiểm tra phù hợp với từng thay đổi và nêu rõ những tổ hợp chưa được xác minh.

### 8.2. Với Vector API hoặc phép toán số

Nếu sản phẩm có kernel vector, kết quả và hiệu năng cần được đánh giá trên CPU thực tế. Dùng species, đường xử lý phần đuôi và tiêu chí sai số đã được đặc tả cho kernel.

Không suy từ một kết quả benchmark trên máy phát triển sang mọi máy triển khai. Khi cấu hình có đường scalar dự phòng, kiểm tra cả tính đúng và việc nhận diện đường đang chạy.

Đây là phần riêng của hợp đồng tính toán. Native access không cấp khả năng SIMD và cũng không thay thế cấu hình module incubator cần thiết.

### 8.3. Với runtime image hoặc container

Runtime tùy chỉnh cần chứa đủ các module mà cấu hình ứng dụng dùng, kể cả service provider hoặc nhánh chỉ được kích hoạt trong vận hành. Phải chạy thử chính image đã tạo.

`jlink` lắp ghép module và dependency vào runtime image; người phát hành chịu trách nhiệm cập nhật image đó. Xem [jlink](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html).

Đối với thư viện native do ứng dụng phân phối, bảo đảm:

- Binary và dependency native có trong image hoặc vị trí triển khai.
- Kiến trúc của image, JVM và binary khớp.
- Runtime C của môi trường đáp ứng yêu cầu binary.
- Tài khoản chạy dịch vụ đọc được tệp cần thiết.
- Cách khởi động và dừng vẫn đúng khi chạy dưới bộ quản lý tiến trình.

Các tệp native của ứng dụng phải được kiểm kê riêng; chỉ có danh sách module Java chưa mô tả đầy đủ chúng.

## 9. Viết tài liệu triển khai có thể làm theo

Tài liệu tốt cần giúp người khác tái tạo cách chạy từ gói phát hành. Mỗi thông tin phải có nguồn xác định, không dùng những chỉ dẫn mơ hồ như “cài Java mới” hoặc “thêm các cờ cần thiết”.

### 9.1. Nội dung tối thiểu của một hồ sơ triển khai

| Phần | Nội dung |
| --- | --- |
| Định danh phát hành | Phiên bản, checksum artifact, cấu hình và binary native. |
| Môi trường hỗ trợ | JDK vendor/build đã kiểm tra, OS, kiến trúc và các yêu cầu native. |
| Bố trí tệp | Vị trí JAR/module, thư viện native, cấu hình và nơi ghi log. |
| Cách khởi động | Lệnh launcher hoặc cấu hình dịch vụ cụ thể. |
| Quyền native access | Module được cấp, lý do và nơi khai báo. |
| Xác minh sẵn sàng | Điều kiện readiness và thao tác nhỏ kiểm tra đường native. |
| Giám sát | Chế độ native/fallback, lỗi, độ trễ và tài nguyên cần theo dõi. |
| Dừng | Ngừng nhận việc, đợi việc đang chạy và giải phóng tài nguyên. |
| Khôi phục | Bộ phiên bản quay về, trình tự và ràng buộc dữ liệu. |
| Xử lý sự cố | Triệu chứng, thông tin cần thu thập và đầu mối phụ trách. |

### 9.2. Ví dụ tệp đối số cho runtime JDK 27

Giả sử bộ phát hành module hóa nằm dưới `/opt/report`, cấu hình có thể dùng tệp `runtime-jdk27.args` với nội dung:

```text
--illegal-native-access=deny
--enable-native-access=com.example.nativebridge
-Dnative.codec.path=/opt/report/native/libcodec.so
--module-path
/opt/report/modules
--module
com.example.report/com.example.report.Main
```

Khởi động bằng đường dẫn tới tệp đối số:

```text
java @/opt/report/config/runtime-jdk27.args
```

`native.codec.path` là thuộc tính do ứng dụng trong ví dụ tự định nghĩa và phải tự đọc. JVM không tự tải thư viện chỉ vì thuộc tính đó tồn tại.

Trên Windows, khi truyền một đối số bắt đầu bằng `@` trong PowerShell, có thể đặt nó trong dấu nháy:

```powershell
java '@C:/apps/report/config/runtime-jdk27.args'
```

Nội dung tệp đối số phải đổi sang các đường dẫn Windows tương ứng, chẳng hạn `C:/apps/report/modules` và `C:/apps/report/native/codec.dll`. Dùng cú pháp quoting phù hợp nếu đường dẫn có khoảng trắng.

Đây là profile cho JDK 27. Nếu hỗ trợ runtime khác, tạo profile đã được kiểm tra cho runtime đó thay vì sao chép nguyên mọi tùy chọn.

### 9.3. Mẫu hồ sơ để điền bằng kết quả thực tế

```text
RELEASE_ID:
JAVA_ARTIFACTS_AND_CHECKSUMS:
NATIVE_ARTIFACTS_AND_CHECKSUMS:
CONFIGURATION_REVISION:

COMPILE_BASELINE:
RUNTIME_VENDOR_AND_FULL_VERSION:
SUPPORTED_OS_AND_ARCHITECTURE:
NATIVE_RUNTIME_REQUIREMENTS:

LAUNCHER_OR_SERVICE_CONFIGURATION:
NATIVE_ACCESS_TARGETS_AND_REASONS:
PREVIEW_OR_INCUBATOR_REQUIREMENTS_IF_ANY:

READINESS_CHECK:
EXPECTED_RESULT:
VALIDATION_EVIDENCE:

RESOURCE_LIMITS_AND_ACCEPTANCE_CRITERIA:
SHUTDOWN_PROCEDURE:
ROLLBACK_BUNDLE:
DATA_COMPATIBILITY_FOR_ROLLBACK:
OPERATIONS_OWNER:
```

Với mục không áp dụng, ghi rõ không áp dụng và lý do. Với mục chưa được kiểm tra, ghi trạng thái đó cùng công việc còn lại. Không biến một ô trống thành một giả định mặc định.

## 10. Chuẩn bị khôi phục cùng với triển khai

Một lần nâng cấp có thể thay cả JDK, dependency Java, binary native và cách khởi động. Quay lại duy nhất file JAR có thể để lại một tổ hợp chưa từng được xác minh.

Bộ khôi phục nên chỉ rõ:

```text
Artifact Java của bản trước
+ dependency tương ứng
+ runtime hoặc image đã dùng
+ binary native tương ứng
+ cấu hình khởi động tương ứng
```

Trước khi cho phép quay về, kiểm tra dữ liệu mà phiên bản mới đã tạo hoặc thay đổi. Nếu bản cũ không đọc được định dạng mới, cần phương án xử lý dữ liệu hoặc chặn việc rollback đơn giản.

Một trình tự dừng điển hình cho dịch vụ có native là:

1. Ngừng nhận công việc mới.
2. Đợi hoặc hủy công việc theo chính sách đã định.
3. Xác nhận native đã ngừng sử dụng buffer và callback.
4. Giải phóng tài nguyên cùng thư viện theo quyền sở hữu.
5. Dừng tiến trình và khởi động bộ phiên bản cần chạy.
6. Thực hiện readiness cùng phép kiểm tra nghiệp vụ nhỏ.

Trình tự cụ thể phụ thuộc thư viện và ứng dụng. Lệnh interrupt hay hủy task Java không tự chứng minh một thao tác native đã kết thúc.

Chọn triển khai từng phần và tiêu chí dừng dựa trên tín hiệu có ý nghĩa: lỗi đầu ra, lỗi native, độ trễ, tăng bộ nhớ toàn tiến trình hoặc readiness thất bại. Người vận hành cần biết tiêu chí và thao tác tiếp theo trước khi phát hành.

## 11. Điều kiện chốt trước khi dùng thực tế

Chỉ đánh dấu một tổ hợp sẵn sàng khi có thể trả lời bằng bằng chứng:

| Câu hỏi | Điều kiện để chốt |
| --- | --- |
| Đã biết chính xác cái gì sẽ chạy chưa? | Có artifact, dependency, runtime và cấu hình được định danh. |
| Mã còn phụ thuộc biến thể cũ của API không? | Đã dùng API phù hợp JDK đích; preview/incubator nếu có được ghi rõ. |
| Ai cần native access? | Đã xác định module thực hiện thao tác và cấu hình quyền tương ứng. |
| Cấu hình có thật sự tới tiến trình ứng dụng không? | Đã chạy bằng launcher hoặc service wrapper triển khai. |
| Nhánh native đã được chạy chưa? | Có kiểm tra load, symbol và lời gọi có kết quả xác định. |
| ABI và vòng đời có hợp đồng rõ không? | Có ánh xạ chữ ký, kích thước, ownership, thread và thứ tự giải phóng. |
| Kết quả và tài nguyên có đạt không? | Có tiêu chí và kết quả kiểm tra trên môi trường được hỗ trợ. |
| Người khác có thể vận hành không? | Có tài liệu khởi động, readiness, theo dõi lỗi và shutdown. |
| Có thể quay lại không? | Có bộ khôi phục và kết luận về tương thích dữ liệu. |

Nếu một mục chưa đạt, ghi cụ thể: vấn đề, tổ hợp bị ảnh hưởng, bằng chứng hiện có, người phụ trách và việc phải hoàn thành. Ví dụ “đã chạy trên Linux x64 nhưng chưa xác minh binary ARM64” mô tả phạm vi rõ hơn một dòng “hỗ trợ đa nền tảng”.

Mục tiêu của hồ sơ triển khai là làm cho phạm vi hỗ trợ, cấu hình và cách vận hành có thể kiểm chứng được trong từng lần phát hành.
