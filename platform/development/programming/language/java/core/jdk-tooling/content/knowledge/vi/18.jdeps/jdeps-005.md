# Phân tích dependency module bằng jdeps

`jdeps` là công cụ dòng lệnh đi kèm JDK để phân tích các dependency ở mức class file, package, archive và Java module. Công cụ đọc bytecode cùng metadata module để xác định một lớp hoặc module tham chiếu đến những kiểu nào, các tham chiếu đó thuộc module nào và ứng dụng cần những module JDK nào để chạy hoặc để tạo custom runtime image bằng `jlink`.

Trong Java Platform Module System (JPMS), một module khai báo dependency tường minh bằng chỉ thị `requires` trong `module-info.java`. Tuy nhiên, khi chuyển ứng dụng cũ từ classpath sang module path hoặc khi chuẩn bị runtime image, chỉ nhìn vào source code và khai báo `requires` có thể chưa đủ. `jdeps` giúp đối chiếu dependency thực tế được thể hiện trong class file với module descriptor, tìm tham chiếu bị thiếu và đề xuất danh sách module cần thiết.

`jdeps` thực hiện phân tích tĩnh. Nó không chạy ứng dụng và không quan sát mọi lớp được tải động trong runtime. Vì vậy, kết quả là cơ sở để hiểu dependency và chuẩn bị cấu hình, sau đó vẫn cần kiểm thử ứng dụng trên môi trường thực tế.

## 1. Module dependency là gì?

Một Java module có thể sử dụng public type được export bởi module khác. Module sử dụng khai báo dependency bằng `requires`:

```java
module com.example.app {
    requires java.sql;
}
```

Trong ví dụ, `com.example.app` cần module `java.sql` để biên dịch và chạy các phần code tham chiếu API JDBC.

Module graph là đồ thị có hướng gồm các module và quan hệ phụ thuộc. Nếu module A yêu cầu B, còn B yêu cầu C, thì C nằm trong dependency graph cần được phân giải khi link A. Module system kiểm tra các quan hệ này để xác định module nào có thể đọc và sử dụng kiểu của module khác.

Một số từ khóa quan trọng trong module descriptor:

| Chỉ thị | Ý nghĩa |
|---|---|
| `requires` | Khai báo module dependency |
| `requires transitive` | Cho phép module phụ thuộc truyền dependency đến các module đọc nó |
| `requires static` | Dependency cần khi biên dịch nhưng có thể không bắt buộc ở runtime |
| `exports` | Cho phép module khác truy cập public type trong package được export |
| `opens` | Cho phép reflective access sâu vào package theo quy tắc module |
| `uses` | Khai báo service mà module sử dụng |
| `provides ... with ...` | Khai báo implementation cung cấp cho một service |

`jdeps` giúp kiểm tra module dependency và những tham chiếu được tìm thấy trong bytecode. Nó không thay thế việc thiết kế module descriptor: lập trình viên vẫn quyết định dependency nào nên là `transitive`, package nào nên export và service nào cần khai báo.

## 2. jdeps phân tích những gì?

`jdeps` có thể phân tích nhiều loại đầu vào:

- Một tệp `.class`.
- Một thư mục chứa class file, thường là exploded module hoặc output của compiler.
- Một JAR.
- Một JMOD.
- Một module có thể phân giải trên module path.

Công cụ có thể báo dependency ở các mức:

| Mức phân tích | Nội dung |
|---|---|
| Class | Lớp nào tham chiếu đến lớp nào |
| Package | Package nào phụ thuộc package nào |
| Archive | JAR/JMOD nào phụ thuộc archive khác |
| Module | Module nào phụ thuộc module nào |
| JDK module | Những module nền tảng Java cần thiết |

Một tham chiếu có thể xuất hiện vì kiểu được dùng trong field, method signature, superclass, interface, annotation, exception hoặc bytecode bên trong method. Tùy tùy chọn, `jdeps` có thể chỉ in dependency ở mức module hoặc hiển thị chi tiết đến package/class.

Kết quả module dependency đặc biệt hữu ích khi:

- Xác định module JDK cần cho ứng dụng.
- Chuẩn bị đầu vào cho `jlink`.
- Kiểm tra một modular JAR khai báo `requires` có hợp lý hay không.
- Phân tích thư viện cũ trước khi tạo module descriptor.
- Tìm tham chiếu đến JDK internal API.
- Điều tra dependency bị thiếu hoặc sai module path.

## 3. Kiểm tra phiên bản và cú pháp cơ bản

`jdeps` nằm trong JDK. Kiểm tra phiên bản:

```sh
jdeps --version
```

Xem trợ giúp:

```sh
jdeps --help
```

Cú pháp tổng quát:

```text
jdeps [options] <path>...
```

Có thể truyền nhiều tệp hoặc archive. Những tùy chọn thường dùng:

| Tùy chọn | Tác dụng |
|---|---|
| `--list-deps` | Liệt kê module dependency |
| `--list-reduced-deps` | Liệt kê dependency ở dạng rút gọn theo module graph |
| `--print-module-deps` | In danh sách module dạng comma-separated |
| `--module-path` | Chỉ định nơi tìm module |
| `--class-path` | Chỉ định nơi tìm dependency trên classpath |
| `--recursive` hoặc `-R` | Phân tích dependency theo chiều đệ quy |
| `-verbose:package` | Hiển thị dependency ở mức package |
| `-verbose:class` | Hiển thị dependency ở mức class |
| `-summary` | Tóm tắt dependency theo archive |
| `--missing-deps` | Tìm dependency không phân giải được |
| `--check` | Kiểm tra module dependency và module descriptor |
| `--jdkinternals` | Tìm việc sử dụng JDK internal API |
| `--multi-release` | Chọn phiên bản trong multi-release JAR để phân tích |

Danh sách tùy chọn chi tiết có thể thay đổi theo phiên bản JDK. Luôn kiểm tra `jdeps --help` của đúng JDK dùng trong build.

## 4. Ví dụ modular application có dependency java.sql

Tạo cấu trúc nguồn:

```text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Nội dung `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

Nội dung `Main.java`:

```java
package com.example.app;

import java.sql.Connection;
import java.sql.SQLException;

public class Main {
    public static String databaseName(Connection connection)
            throws SQLException {
        return connection.getMetaData().getDatabaseProductName();
    }

    public static void main(String[] args) {
        System.out.println("Module dependency analysis");
    }
}
```

Class `Main` tham chiếu `Connection` và `SQLException` thuộc module `java.sql`. Phương thức `databaseName` chỉ mô tả cách dùng API JDBC; chương trình main không cần mở kết nối database nên ví dụ có thể chạy mà không cần JDBC driver.

Biên dịch module:

```sh
mkdir -p mods
javac --module-source-path src -d mods -m com.example.app
```

Kết quả là exploded module:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

Chạy module trên module path:

```sh
java --module-path mods -m com.example.app/com.example.app.Main
```

Stdout:

```text
Module dependency analysis
```

Ví dụ này dùng cú pháp module và công cụ có từ Java 9; các lệnh vẫn phù hợp với JDK 17+.

## 5. Liệt kê module dependency bằng --list-deps

Để xem module mà một modular application cần, dùng:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --list-deps
```

Trên Windows PowerShell, dấu phân tách module path là dấu chấm phẩy:

```powershell
jdeps --module-path "$env:JAVA_HOME\jmods;mods" --module com.example.app --list-deps
```

Trong ví dụ, module path gồm:

- `$JAVA_HOME/jmods`: các JMOD của JDK đang dùng.
- `mods`: thư mục chứa exploded module `com.example.app`.
- `--module com.example.app`: module được phân tích.
- `--list-deps`: yêu cầu in module dependency.

Danh sách đầu ra có thể chứa `java.base`, `java.sql` và các module được kéo theo bởi quan hệ phụ thuộc trong JDK. Kết quả cụ thể có thể thay đổi theo phiên bản JDK và cấu trúc dependency; không nên sao chép một danh sách module mẫu làm cấu hình cố định.

`java.base` là module nền tảng mà mọi module Java đều phụ thuộc trực tiếp hoặc gián tiếp. Khi ứng dụng dùng API JDBC, `java.sql` là dependency quan trọng cần có trong module graph.

## 6. In danh sách module cho jlink bằng --print-module-deps

Khi chuẩn bị custom runtime image, tùy chọn hữu ích là `--print-module-deps`:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps
```

Tùy chọn này in tên module dưới dạng danh sách phân tách bằng dấu phẩy, thuận tiện để đưa vào `jlink --add-modules` hoặc lưu vào build script.

Ví dụ quy trình:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps

jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app \
      --output app-image
```

`jlink` tự phân giải dependency của root module `com.example.app`. Danh sách từ `jdeps --print-module-deps` hữu ích để hiểu các module cần thiết và xây dựng cấu hình runtime, nhưng không thay thế kiểm thử. Nếu ứng dụng tải module bằng reflection, plugin hoặc tên lớp lấy từ cấu hình, cần bổ sung module tương ứng bằng cấu hình link phù hợp.

Không nên tự động giả định rằng mọi module được tìm thấy trong một lần phân tích tĩnh đều là toàn bộ dependency runtime. Đặc biệt, những module chỉ được nạp theo nhánh chức năng hiếm gặp có thể cần kiểm thử riêng.

## 7. Phân biệt --list-deps, --list-reduced-deps và --print-module-deps

Ba tùy chọn này có mục đích gần nhau nhưng dạng đầu ra khác nhau:

| Tùy chọn | Dùng khi |
|---|---|
| `--list-deps` | Muốn xem danh sách module dependency dễ đọc |
| `--list-reduced-deps` | Muốn xem danh sách đã rút gọn dựa trên quan hệ transitive của module graph |
| `--print-module-deps` | Muốn nhận chuỗi module phân tách bằng dấu phẩy để dùng trong script/link |

Với module có `requires transitive`, một dependency có thể đã được bao hàm qua module khác trong graph. Danh sách reduced có thể loại những quan hệ dư thừa theo quy tắc module resolution. Điều đó không có nghĩa dependency đó không tồn tại; nó chỉ có nghĩa graph có thể biểu diễn gọn hơn.

Khi cần chẩn đoán, bắt đầu bằng `--list-deps` để dễ đọc. Khi chuẩn bị danh sách module cho quy trình build, xem `--print-module-deps`. Khi cần so sánh cách biểu diễn graph, kiểm tra `--list-reduced-deps`.

## 8. Phân tích JAR chạy trên classpath

Ứng dụng cũ có thể chưa có `module-info.java`. `jdeps` vẫn phân tích được JAR và ánh xạ các tham chiếu đến module JDK.

Giả sử có:

```text
app.jar
lib/
├── client.jar
└── common.jar
```

Phân tích dependency của JAR:

```sh
jdeps --class-path "lib/*" --list-deps app.jar
```

`--class-path` chỉ định dependency mà `jdeps` có thể dùng để phân giải các class reference ngoài JAR. Wildcard `lib/*` là cú pháp classpath phổ biến để bao gồm các JAR trong thư mục.

Muốn xem dependency chi tiết theo package:

```sh
jdeps --class-path "lib/*" -verbose:package app.jar
```

Muốn xem từng class:

```sh
jdeps --class-path "lib/*" -verbose:class app.jar
```

Khi phân tích classpath application, kết quả module dependency của JDK có thể dùng để định hướng module hóa. Tuy nhiên, các JAR bên thứ ba không tự động trở thành module JDK. Chúng có thể cần tiếp tục được phân phối trên classpath, được chuyển thành modular JAR hoặc được đưa vào module path theo quy tắc phù hợp.

## 9. Phân tích đệ quy và bộ lọc

`jdeps` có thể phân tích sâu hơn các archive phụ thuộc. Dùng `--recursive` hoặc `-R` khi muốn theo dependency qua các archive có thể tìm thấy trên classpath/module path:

```sh
jdeps --recursive --class-path "lib/*" --list-deps app.jar
```

Đệ quy hữu ích khi muốn hiểu thư viện mà ứng dụng sử dụng lại kéo theo những dependency nào. Tuy nhiên, nó có thể tạo báo cáo dài hơn và làm phạm vi phân tích rộng hơn.

Để điều chỉnh mức chi tiết:

```sh
jdeps -verbose:package --class-path "lib/*" app.jar
jdeps -verbose:class --class-path "lib/*" app.jar
```

Các bộ lọc có thể giúp tập trung vào phần dependency cần xem. Ví dụ, `-filter:archive`, `-filter:package`, `-filter:module` và `-filter:none` điều khiển cách hiển thị dependency nội bộ hoặc bên ngoài theo mức tương ứng. Cú pháp cụ thể nên được xác nhận bằng `jdeps --help` của JDK hiện tại.

Nếu báo cáo quá dài, hãy bắt đầu ở mức module hoặc package rồi chỉ chuyển sang class-level khi cần xác định chính xác lớp tạo ra dependency.

## 10. Tìm dependency bị thiếu bằng --missing-deps

Khi JAR tham chiếu một lớp không thể phân giải, có thể dùng:

```sh
jdeps --missing-deps --class-path "lib/*" app.jar
```

Tùy chọn này tập trung vào dependency bị thiếu. Nó hữu ích khi:

- Một JAR phụ thuộc vào thư viện khác nhưng thư viện đó không có trên classpath.
- Phiên bản dependency không còn chứa một lớp được ứng dụng tham chiếu.
- Build hoặc packaging bỏ sót một artifact.
- Ứng dụng chạy được ở máy phát triển nhưng thiếu lớp ở môi trường triển khai.

Nếu không cung cấp đúng classpath/module path, công cụ có thể báo thiếu lớp dù dependency thực tế tồn tại ở nơi khác. Trước khi kết luận thư viện bị thiếu, hãy kiểm tra đường dẫn và phiên bản artifact.

`--ignore-missing-deps` có thể bỏ qua cảnh báo về dependency không phân giải được trong một số tình huống phân tích. Đây là lựa chọn để tiếp tục kiểm tra các dependency còn lại; nó không khắc phục dependency bị thiếu và không nên được dùng để tuyên bố ứng dụng đã sẵn sàng chạy.

## 11. Kiểm tra module descriptor với --check

Với modular application, `--check` giúp kiểm tra module dependency và descriptor hiện tại:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --check com.example.app
```

Công cụ hiển thị dependency graph liên quan và có thể đề xuất descriptor với các dependency được đánh giá là cần thiết. Điều này giúp phát hiện khai báo `requires` dư thừa hoặc các dependency cần được xem xét.

Khi đọc kết quả:

1. Xem module đang được kiểm tra.
2. Đối chiếu các module được yêu cầu trong descriptor.
3. Kiểm tra module nào được sử dụng trực tiếp qua bytecode.
4. Xem đề xuất descriptor của công cụ.
5. Đánh giá ý nghĩa API trước khi sửa `module-info.java`.

Không xóa `requires` chỉ vì nó không xuất hiện trong một báo cáo tĩnh. Dependency có thể cần cho reflection, service binding, cấu hình runtime hoặc code path không xuất hiện trong tập class file được phân tích. Ngược lại, khai báo dư thừa có thể làm module graph rộng hơn và làm tăng coupling.

Sau khi chỉnh descriptor, biên dịch lại và chạy test trên module path để xác nhận.

## 12. Tạo module descriptor cho thư viện cũ

Một thư viện JAR cũ có thể không có `module-info.class`. `jdeps` có thể đề xuất module descriptor bằng `--generate-module-info`.

Ví dụ:

```sh
jdeps --generate-module-info generated-modules legacy-library.jar
```

Công cụ tạo cấu trúc output dưới thư mục `generated-modules` với tệp `module-info.java` được đề xuất cho archive.

Nếu thư viện cần được xem như open module để hỗ trợ reflective access sâu theo yêu cầu tương thích, có thể xem `--generate-open-module`:

```sh
jdeps --generate-open-module generated-open-modules legacy-library.jar
```

Descriptor sinh ra là điểm bắt đầu, không phải kết quả thiết kế đã được duyệt. Hãy đọc và chỉnh sửa:

- Tên module được đề xuất.
- Các chỉ thị `requires`.
- Package cần `exports`.
- Package cần `opens` cho reflection.
- Các service `uses` và `provides` nếu thư viện có dùng.
- Các dependency optional hoặc chỉ cần ở compile-time.

Sau khi hoàn thiện descriptor, biên dịch module-info và đóng gói lại theo quy trình modular JAR/JMOD phù hợp. Không giả định `jdeps` có thể tự hiểu mọi quy tắc API hoặc mục tiêu tương thích của thư viện.

## 13. Tìm JDK internal API bằng --jdk-internals

Một rủi ro khi nâng cấp Java là ứng dụng phụ thuộc vào JDK internal API, chẳng hạn lớp trong package `sun.*` hoặc `com.sun.*` không được cam kết là API công khai ổn định.

Dùng:

```sh
jdeps --jdk-internals app.jar
```

Công cụ có thể báo lớp hoặc package nội bộ được tham chiếu và gợi ý API công khai thay thế nếu có.

Vì sao cần xử lý:

- Internal API có thể thay đổi hoặc bị loại bỏ giữa các bản JDK.
- Module encapsulation hạn chế truy cập đến package nội bộ.
- Ứng dụng có thể cần tùy chọn mở module trong quá trình chạy nếu còn phụ thuộc cũ.
- Các cờ mở package tạm thời không thay thế việc chuyển sang API công khai.

Nếu kết quả chỉ ra dependency nội bộ, hãy tìm API được hỗ trợ trong Java SE hoặc thư viện chính thức. Chỉ dùng cơ chế mở module như `--add-exports` hoặc `--add-opens` khi đã hiểu rõ phạm vi và có lý do tương thích; xem đó là biện pháp chuyển tiếp, không phải giải pháp dài hạn.

## 14. Phân tích API công khai với --api-only

`--api-only` giới hạn phân tích vào các dependency xuất hiện trong API được công khai, ví dụ kiểu trong public/protected signature. Điều này hữu ích khi muốn hiểu dependency nào trở thành một phần của hợp đồng API mà module cung cấp.

Ví dụ:

```sh
jdeps --api-only --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app
```

So sánh kết quả API-only với phân tích đầy đủ:

- API-only cho thấy dependency có thể ảnh hưởng đến người dùng module khi biên dịch code phụ thuộc.
- Phân tích đầy đủ còn bao gồm tham chiếu nội bộ trong implementation.
- Một module có thể cần dependency nội bộ để chạy nhưng không nhất thiết phải để lộ dependency đó trong public API.

Đây là cơ sở để xem xét `requires transitive`. Nếu public API của module A dùng kiểu được export bởi module B, người dùng A có thể cần đọc B để biên dịch. Tuy nhiên, không nên tự động biến mọi dependency thành transitive; hãy xem xét API contract và thiết kế module.

## 15. Multi-release JAR và --multi-release

Multi-release JAR có thể chứa class file khác nhau cho các phiên bản Java khác nhau trong thư mục `META-INF/versions/N`. Khi phân tích, cần chọn phiên bản phù hợp:

```sh
jdeps --multi-release 17 --list-deps library.jar
```

Tùy chọn `--multi-release` yêu cầu `jdeps` phân tích phần class dành cho Java release được chỉ định. Điều này hữu ích khi:

- Một thư viện có implementation riêng cho Java 9, 11, 17 hoặc release khác.
- Dependency của implementation theo phiên bản có thể khác nhau.
- Cần kiểm tra JAR theo runtime target cụ thể.

Hãy dùng phiên bản tương ứng với runtime mà sản phẩm hỗ trợ và xác nhận JAR thực sự được đánh dấu multi-release trong manifest bằng `Multi-Release: true`. Phân tích base entry và phân tích entry versioned có thể cho kết quả khác nhau.

Không dùng một kết quả phân tích cho Java 17 để khẳng định mọi implementation của JAR đều có cùng dependency trên Java 21 hoặc release khác.

## 16. Dependency tĩnh và dependency được nạp động

`jdeps` phân tích tham chiếu có thể suy ra từ class file và metadata module. Có những dependency runtime không xuất hiện như một class reference tĩnh đơn giản:

- Tên lớp được đọc từ file cấu hình rồi nạp bằng `Class.forName`.
- Plugin được phát hiện từ thư mục hoặc registry riêng.
- Framework tạo proxy hoặc lớp bằng bytecode generation.
- JNI tải native library theo tên.
- Service provider được phát hiện qua cơ chế service loading.
- Dependency chỉ được kích hoạt theo một feature flag hoặc nhánh nghiệp vụ.

Ví dụ:

```java
String implementation = configuration.get("driver.class");
Class<?> type = Class.forName(implementation);
Object driver = type.getDeclaredConstructor().newInstance();
```

`jdeps` có thể thấy tham chiếu đến `Class` và reflection API, nhưng không nhất thiết biết giá trị runtime của `implementation`. Do đó, nó không thể tự suy ra mọi module hoặc JAR cần thiết cho chuỗi lớp lấy từ cấu hình.

Cách xử lý:

1. Tìm cấu hình chứa tên lớp và provider.
2. Kiểm tra module descriptor có khai báo service `uses`/`provides` hay không.
3. Xác định module cần thiết trong các luồng chức năng.
4. Thêm module phù hợp vào module path hoặc root module của `jlink`.
5. Chạy integration test trên runtime image đã tạo.

Với service binding, xem xét `jlink --bind-services` khi ứng dụng dùng `ServiceLoader` và cần các provider trong image. `jdeps` là một phần của phân tích, không phải bằng chứng rằng mọi dependency động đã được tìm thấy.

## 17. Phân biệt jdeps với Maven/Gradle dependency tree

`jdeps` và build tool cùng giúp hiểu dependency, nhưng dữ liệu chúng phân tích khác nhau:

| Công cụ | Dữ liệu chính | Trả lời câu hỏi |
|---|---|---|
| `jdeps` | Class file, archive và module descriptor | Bytecode/module đang tham chiếu những kiểu hoặc module nào? |
| Maven dependency tree | Khai báo dependency và quy tắc resolution của Maven | Artifact nào được kéo vào build, qua dependency nào? |
| Gradle dependencies | Configuration và dependency graph của Gradle | Dependency nào thuộc compile/runtime/test configuration? |
| `jlink` | Module graph đã phân giải | Tạo runtime image chứa những module nào? |

Một dependency có trong Maven/Gradle graph có thể không được tham chiếu trong bytecode của một đường chạy cụ thể. Ngược lại, một lớp được nạp bằng reflection có thể không hiện ra như dependency tĩnh trong kết quả `jdeps`.

Khi cần gỡ thư viện khỏi ứng dụng, hãy kết hợp build-tool dependency tree với phân tích bytecode và test. Đừng xóa một dependency chỉ vì `jdeps` không hiển thị nó; nó có thể được dùng lúc runtime qua cấu hình, service provider hoặc framework.

## 18. Từ kết quả jdeps đến custom runtime với jlink

Một quy trình thường gặp:

```text
Source code
    |
    v
javac
    |
    v
Class files / modular JAR
    |
    v
jdeps
    |
    v
Module dependency report
    |
    v
Review dynamic dependencies
    |
    v
jlink
    |
    v
Custom runtime image
```

Ví dụ lệnh đầy đủ:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps

jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app \
      --output app-image

app-image/bin/java --list-modules
app-image/bin/java -m com.example.app/com.example.app.Main
```

Với Windows, thay dấu phân tách module path bằng dấu chấm phẩy và gọi executable trong thư mục `app-image\bin`.

`jlink` tự phân giải các dependency được khai báo trong module graph. Danh sách từ `jdeps` giúp kiểm tra kết quả phân tích và chuẩn bị cấu hình, còn các module được nạp động phải được xử lý riêng. Sau khi link, chạy test trên image chứ không chỉ chạy bằng JDK đầy đủ của máy phát triển.

## 19. Xuất báo cáo dependency bằng DOT

`jdeps` có thể xuất dữ liệu đồ thị dependency để xem bằng công cụ hỗ trợ Graphviz/DOT.

Ví dụ:

```sh
jdeps --dot-output dependency-report \
      --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app
```

Thư mục output chứa các tệp mô tả quan hệ dependency theo định dạng DOT. Có thể chuyển chúng thành hình bằng Graphviz nếu công cụ này đã được cài:

```sh
dot -Tpng dependency-report/com.example.app.dot \
    -o dependency-report/com.example.app.png
```

Đồ thị hữu ích khi module có nhiều dependency hoặc khi muốn phát hiện coupling giữa các package. Tên và số lượng file DOT sinh ra phụ thuộc đầu vào và phiên bản công cụ.

Khi xem graph, chú ý chiều mũi tên và phạm vi module/package. Một đồ thị lớn không nhất thiết có nghĩa ứng dụng chạy chậm; nó mô tả quan hệ tham chiếu, không phải profile hiệu năng runtime.

## 20. Lỗi thường gặp khi dùng jdeps

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy module | Module path thiếu JMOD/JAR hoặc tên module sai | Kiểm tra `--module-path` và descriptor bằng `jar --describe-module`/`jmod describe` |
| Missing dependency | Thiếu JAR trong classpath hoặc dependency không tương thích | Bổ sung đúng artifact/version rồi chạy lại |
| Không thấy module được tải động | Phân tích tĩnh không biết tên lớp lấy từ cấu hình/reflection | Kiểm tra cấu hình, ServiceLoader và test runtime |
| Kết quả quá dài | Dùng class-level hoặc recursive trên nhiều archive | Bắt đầu bằng `--list-deps` hoặc `-summary` rồi tăng chi tiết |
| Kết quả khác giữa JDK | Module graph hoặc multi-release entry khác theo release | Ghi rõ JDK và dùng `--multi-release` phù hợp |
| `--check` đề xuất bỏ requires | Dependency không được thấy trong static references của tập phân tích | Kiểm tra reflection, service và API contract trước khi sửa |
| `--generate-module-info` tạo descriptor chưa dùng được | Thư viện có dependency hoặc package export/open đặc thù | Review descriptor, bổ sung chỉ thị và biên dịch lại |
| Báo JDK internal API | Thư viện tham chiếu package không được cam kết công khai | Tìm API thay thế và nâng dependency |
| `jlink` thiếu module sau khi dùng kết quả jdeps | Có dependency runtime động chưa được tính | Bổ sung module/provider cần thiết và test trên image |
| `jdeps` không phân tích được archive | Tệp hỏng, định dạng không hỗ trợ hoặc class version quá mới so với tool | Dùng JDK tương thích và xác nhận archive hợp lệ |

Khi chẩn đoán, kiểm tra đầu vào trước: đúng file, đúng JDK, đúng classpath/module path và đúng release của multi-release JAR. Sau đó mới kết luận dependency thiếu hay descriptor sai.

## 21. Quy trình phân tích dependency có thể lặp lại

1. Ghi nhận phiên bản JDK bằng `jdeps --version` và `java -version`.
2. Xác định đầu vào là class directory, JAR, JMOD hay module.
3. Cung cấp đầy đủ classpath hoặc module path cần thiết.
4. Chạy `--list-deps` để xem dependency module ở mức tổng quan.
5. Chạy `--print-module-deps` nếu cần danh sách cho quy trình `jlink`.
6. Dùng `-verbose:package` hoặc `-verbose:class` để tìm nguồn tham chiếu cụ thể.
7. Chạy `--missing-deps` để phát hiện dependency chưa phân giải.
8. Với module tường minh, dùng `--check` để review `requires`.
9. Với JAR cũ, xem xét `--generate-module-info` và chỉnh descriptor thủ công.
10. Chạy `--jdkinternals` để phát hiện phụ thuộc vào API nội bộ.
11. Kiểm tra dependency động, service provider, reflection, JNI và cấu hình.
12. Tạo runtime image bằng `jlink` và chạy test trên image đó.
13. Lưu lệnh, phiên bản JDK và báo cáo để có thể tái lập kết quả.

Khi chạy trong CI, nên ghi lại JDK version, lệnh jdeps, module path và artifact checksum. Điều này giúp so sánh kết quả khi dependency hoặc JDK được nâng cấp.

## 22. Checklist

- [ ] Đã xác định đúng JDK và phiên bản `jdeps`.
- [ ] Đã xác định đầu vào cần phân tích.
- [ ] Đã cung cấp đúng classpath/module path.
- [ ] Đã dùng `--list-deps` để xem module dependency.
- [ ] Đã dùng `--print-module-deps` nếu chuẩn bị `jlink`.
- [ ] Đã xem chi tiết package/class khi cần.
- [ ] Đã kiểm tra dependency bị thiếu.
- [ ] Đã review module descriptor bằng `--check`.
- [ ] Đã xem xét module descriptor sinh ra cho thư viện cũ.
- [ ] Đã kiểm tra JDK internal API.
- [ ] Đã chọn đúng release cho multi-release JAR.
- [ ] Đã xem xét dependency động và service provider.
- [ ] Đã chạy ứng dụng trên runtime image cuối.

## 23. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jdeps` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Oracle JDK 21 Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Java Platform Module System — Java Language and JVM Specifications: https://docs.oracle.com/javase/specs/

`jdeps` giúp nhìn rõ mối quan hệ giữa bytecode, archive và Java module. Khi kết hợp danh sách dependency, kiểm tra descriptor, tìm internal API và xem xét các thành phần được nạp động, bạn có thể xây dựng module graph đáng tin cậy và chuẩn bị custom runtime image phù hợp với ứng dụng.