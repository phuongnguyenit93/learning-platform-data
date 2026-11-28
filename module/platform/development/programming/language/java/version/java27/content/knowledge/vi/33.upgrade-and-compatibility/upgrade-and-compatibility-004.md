# Dùng jdeps, jdeprscan và cảnh báo biên dịch để tìm điểm cần xử lý

Khi nâng một ứng dụng từ JDK cũ lên Java 27, việc chạy thành công lệnh `java --version` hoặc biên dịch một module không đủ để kết luận hệ thống đã tương thích. Các thay đổi có thể đến từ **API bị deprecated hoặc loại bỏ**, phụ thuộc vào **JDK internal APIs**, thư viện bên ngoài chưa hỗ trợ JDK mới, thay đổi cách resolve module, hoặc những cảnh báo về kiểu dữ liệu và quyền truy cập bị bỏ sót từ lâu.

JDK cung cấp ba công cụ có thể dùng ngay để **phát hiện sớm** những nhóm vấn đề này:

- **`jdeps`** phân tích **phụ thuộc tĩnh từ bytecode**: class/module/JAR cần những API và module nào, có tham chiếu đến API nội bộ của JDK hay dependency bị thiếu không?
- **`jdeprscan`** quét **bytecode** để tìm việc sử dụng các **API Java SE đã deprecated**, kể cả khi chỉ có artifact đã biên dịch và không có source.
- **`javac` với `-Xlint`, `-Werror` và `--release`** giúp kiểm tra **mã nguồn khi biên dịch**, phát hiện API deprecated/for-removal, unchecked conversions, raw types và giới hạn source/API/bytecode đối với bản Java đích.

Đây là bài học của chương **Nâng cấp và tương thích Java 27**, thuộc module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Mọi ví dụ tập trung vào cách rà soát, phân loại và sửa mã để dùng những API còn được hỗ trợ trong Java 27; những đoạn mã sử dụng API cũ chỉ nhằm minh họa **điều cần loại bỏ**, không phải hướng dẫn phát triển mới bằng API legacy.

## 1. Tương thích có nhiều lớp: không chỉ “chạy được”

Một dự án có thể biên dịch bằng JDK 27 nhưng vẫn có vấn đề ở môi trường production:

| Lớp tương thích | Câu hỏi cần trả lời | Bằng chứng cần thu thập |
| --- | --- | --- |
| **Source** | Source còn hợp lệ với ngôn ngữ và API Java 27? | `javac --release 27`, compiler errors/warnings |
| **Bytecode/runtime** | Class files do runtime thực tế đọc được? | Class-file version, startup/smoke tests trên JDK đích |
| **API lifecycle** | Có gọi API đã deprecated hoặc for removal? | `jdeprscan`, `javac -Xlint:deprecation,removal` |
| **JDK internals** | Có phụ thuộc `sun.*`, `jdk.internal.*` hoặc API không được hỗ trợ? | `jdeps --jdk-internals`, review code/config |
| **Dependency graph** | Có class/JAR/module thiếu khi đóng gói? | `jdeps --missing-deps`, build dependency resolution |
| **Module boundaries** | Có lỗi đọc module, export hoặc deep reflection không? | `jdeps`, compile/runtime tests, JPMS errors |
| **Third-party ecosystem** | Framework/driver/agent/native library đã hỗ trợ JDK 27? | Release notes, dependency inventory, integration tests |
| **Hành vi nghiệp vụ** | Lưu dữ liệu, TLS, serialization, thời gian và kết quả vẫn đúng? | Regression, integration, security và performance tests |

**Không công cụ nào trong ba công cụ chứng minh tất cả các lớp tương thích.** `jdeps` và `jdeprscan` là **static analysis**, không thực thi giao dịch nghiệp vụ. `javac` kiểm tra được source mình đang biên dịch, không tự kiểm tra toàn bộ thư viện nhị phân đã publish.

### 1.1. Ba trạng thái khác nhau của API

Hãy phân biệt:

1. **Supported/public API**: API được công bố qua các module/package có hợp đồng sử dụng phù hợp.
2. **Deprecated API**: vẫn có thể tồn tại để tương thích nhưng đã được khuyến nghị tránh dùng; không suy ra nó đã bị xóa.
3. **Deprecated for removal**: có tín hiệu mạnh hơn về dự định loại bỏ trong tương lai; cần ưu tiên xử lý.
4. **Removed API**: không còn có trên JDK đích; code có thể lỗi compile, linkage hoặc runtime, không nhất thiết sinh warning.
5. **JDK internal API**: phụ thuộc implementation, có thể bị encapsulated hoặc thay đổi không theo hợp đồng public API; nó **không đồng nghĩa** với deprecated.

`@Deprecated(forRemoval = true)` không tự động quy định thời điểm xóa cụ thể. Công cụ cho biết *điểm nghi vấn*, còn quyết định sửa dựa trên **API docs, hướng dẫn migration và tác động thực tế**.

## 2. Vai trò của ba công cụ trong một quy trình

```text
   Source code + compiled classes/JARs + dependency inventory
                         |
            +------------+--------------+
            |            |              |
            v            v              v
         javac          jdeps        jdeprscan
        -Xlint         --jdk-internals  --release 27
        --release      --missing-deps   --for-removal
            |            |              |
            v            v              v
      Source warnings  Dependency     Java SE API
      / compile errors graph          deprecations
            |            |              |
            +------------+--------------+
                         |
                         v
               Phân loại & ưu tiên
                         |
                         v
           Sửa source / đổi dependencies
                         |
                         v
              Recompile + re-scan
                         |
                         v
             Test ứng dụng trên Java 27
```

Một thứ tự thực tế:

1. **Inventory** các artifact đang deploy và chọn một JDK 27/toolchain cụ thể.
2. Chạy **`jdeps`** trên JAR/class files có thật để tìm internals, phụ thuộc thiếu hoặc module liên quan.
3. Chạy **`jdeprscan`** để rà việc sử dụng API Java SE deprecated/for removal trong bytecode.
4. Biên dịch mã nguồn bằng **`javac` hoặc compiler do build tool điều phối**, bật warning categories phù hợp.
5. Sửa mã, nâng dependency hoặc thay thiết kế; **chạy lại ba nhóm kiểm tra** và test runtime.

Không nên bỏ qua kết quả của một công cụ chỉ vì hai công cụ còn lại không báo gì: chúng **không tìm cùng một loại lỗi**.

## 3. Chuẩn bị đầu vào: phiên bản JDK, artifact và classpath

Trước khi rà soát, xác nhận các công cụ được lấy từ **JDK 27 đang được dùng để nâng cấp**:

```shell
java --version
javac --version
jdeps --version
jdeprscan --version
```

`jdeps` và `jdeprscan` là **công cụ JDK** (thường dưới thư mục `bin` của JDK), không phải công cụ nằm trong mọi runtime image tối giản. Nếu một container custom chỉ có những module runtime được chọn, hãy chạy công cụ tại **máy build/CI có JDK đầy đủ**.

Đầu vào thường là:

```text
build/
  classes/
    java/
      main/
        com/example/orders/OrderService.class
  libs/
    orders-app.jar
dependencies/
  client-library.jar
  database-driver.jar
```

Đây là **cấu trúc ví dụ**, không phải đường dẫn bắt buộc. Phải biết `orders-app.jar` là **thin JAR** chỉ chứa code của ứng dụng, **fat/uber JAR** chứa dependencies bên trong hay modular JAR; cách chuẩn bị `--class-path`/`--module-path` sẽ khác nhau.

### 3.1. Luôn dùng đúng artifact có thể deploy

- Nếu chỉ quét `src/main/java` bằng `jdeps`, sẽ không được gì: **`jdeps` phân tích bytecode**, không phân tích source code.
- Nếu quét JAR của một phiên bản cũ nhưng deploy build mới, báo cáo không đại diện cho release hiện tại.
- Nếu quét mỗi artifact ứng dụng mà không xem dependencies, có thể bỏ sót thư viện nhị phân trực tiếp dùng API nội bộ.
- Nếu artifact là **multi-release JAR**, phải chọn một version view phù hợp với runtime để phân tích đúng các class files được ưu tiên.

Không chạy các lệnh xây dựng trong bài như một bước tự động của nhiệm vụ soạn nội dung này; đây là **lệnh dành cho người học áp dụng vào dự án của họ**.

### 3.2. Path separator trên các hệ điều hành

Đường dẫn nhiều phần tử dùng dấu phân cách khác nhau:

```text
Linux/macOS: lib/a.jar:lib/b.jar
Windows:     lib\a.jar;lib\b.jar
```

Khi copy lệnh từ tài liệu sang CI, hãy điều chỉnh separator và quoting; không nên cho rằng `:` trong Unix tương đương `;` trong Windows. Các command snippets tiếp theo giả định shell Unix trừ nơi có ví dụ Windows riêng.

## 4. `jdeps`: đọc phụ thuộc từ bytecode

`jdeps` (Java class dependency analyzer) có thể phân tích `.class`, thư mục chứa các classes, JAR hoặc module và hiển thị phụ thuộc ở mức **module, package hoặc class**.

Ví dụ:

```shell
# Phân tích các packages/modules mà JAR tham chiếu tĩnh.
jdeps build/libs/orders-app.jar

# Tóm tắt phụ thuộc.
jdeps -summary build/libs/orders-app.jar

# Xem ở mức class.
jdeps -verbose:class build/libs/orders-app.jar

# Xem mọi liên kết class được phân tích mà không lọc thông thường.
jdeps -verbose build/libs/orders-app.jar
```

Chỉ sử dụng các lệnh khi file JAR đó thực sự tồn tại. `jdeps` hiển thị dependency graph theo bytecode, nhưng không tự xác nhận service ngoài, database, runtime config hoặc reflection đang hoạt động.

Một output dạng minh họa:

```text
orders-app.jar -> java.base
orders-app.jar -> java.sql
   com.example.orders (orders-app.jar)
      -> java.lang                  java.base
      -> java.sql                   java.sql
```

Điều này cho biết artifact dùng package thuộc `java.sql`; **không** chứng minh database driver đã có ở runtime hoặc kết nối tới database thành công.

### 4.1. `--api-only` khác phân tích toàn bộ lời gọi

`--api-only` giới hạn phân tích vào **public/protected API signatures** của public classes, ví dụ kiểu tham số và return type. Nó hữu ích khi đánh giá phần **API mà thư viện công bố**:

```shell
jdeps --api-only -verbose:class build/libs/public-library.jar
```

Không dùng `--api-only` để kết luận **implementation bên trong** không có dependency nguy hiểm; cần phân tích đầy đủ khi muốn tìm usages trong method bodies. Với mục tiêu phát hiện JDK internal APIs, dùng `--jdk-internals` theo mục 5.

### 4.2. Xuất biểu đồ phụ thuộc

`jdeps` có thể tạo graph ở định dạng DOT:

```shell
jdeps --dot-output out/jdeps-graph build/libs/orders-app.jar
```

Lệnh sẽ **ghi file** vào thư mục được chỉ định (bao gồm các `.dot` files). Vì mục đích chỉ là minh họa, không cần thực thi trên workspace của bài học; khi áp dụng thực tế, ghi vào **thư mục báo cáo build riêng** và quản lý artifact retention.

## 5. Tìm JDK internal APIs bằng `jdeps --jdk-internals`

Một rủi ro nâng cấp lớn là ứng dụng hoặc thư viện gọi các lớp **không thuộc API public được hỗ trợ**, chẳng hạn một số lớp dưới `sun.*` hoặc `jdk.internal.*`. Chúng có thể hoạt động trên một JDK cũ hoặc nhờ cấu hình đặc biệt, nhưng Java Platform Module System (JPMS) có thể ngăn truy cập khi nâng cấp.

```shell
jdeps --jdk-internals build/libs/orders-app.jar
```

Nếu ứng dụng có dependencies liên quan, cung cấp classpath/module path tương ứng:

```shell
jdeps --jdk-internals \
  --class-path "dependencies/client-library.jar:dependencies/database-driver.jar" \
  build/libs/orders-app.jar
```

Ví dụ output minh họa:

```text
orders-app.jar -> java.base
  com.example.legacy.LegacyCodec -> jdk.internal.misc.Unsafe  JDK internal API
```

**Không dựa vào từng chữ của output minh họa**: label và tập lớp bị phân loại phụ thuộc JDK, artifact và cách cấu hình. Phần cốt lõi là **tham chiếu đến API nội bộ** được phát hiện.

### 5.1. Cách xử lý khi phát hiện internals

1. Xác định **ai sở hữu call site**: source của ứng dụng, thư viện vendor, agent hay code đã generated.
2. Nếu là **code ứng dụng**, chuyển sang **API public được hỗ trợ** khi có cách thay thế tương đương.
3. Nếu là **dependency**, kiểm tra bản release hỗ trợ JDK 27 hoặc yêu cầu nhà cung cấp sửa.
4. Nếu có cấu hình runtime như `--add-exports` hoặc `--add-opens`, xem chúng như **khoản nợ kỹ thuật có phạm vi và thời hạn**, không phải bằng chứng hệ thống đã tương thích bền vững.
5. Chạy lại `jdeps` và kiểm thử chức năng để bảo đảm thay thế giữ đúng behavior.

**Đừng tự suy rằng đổi `sun.*` thành `jdk.internal.*` là đã sửa.** Cả hai có thể là internal và chịu strong encapsulation.

### 5.2. `--jdk-internals` không tìm tất cả loại truy cập động

`jdeps` phát hiện **tham chiếu tĩnh trong bytecode**. Mã chỉ tạo tên class từ `String` và gọi reflection, tải native library qua JNI, hoặc dùng `ServiceLoader`/cấu hình plugin có thể không tạo dependency edge rõ ràng.

Vì vậy, `jdeps --jdk-internals` không có output **không đảm bảo** application không gặp `InaccessibleObjectException`, `IllegalAccessError` hay lỗi runtime liên quan modules. Phải có integration/smoke tests thực tế.

## 6. Phát hiện thiếu dependency bằng `jdeps --missing-deps`

Không ít lỗi sau nâng cấp là do packaging: một library có trên máy developer nhưng không có trong container, JAR đã đổi tên, hoặc module không được resolve.

```shell
jdeps --missing-deps build/libs/orders-app.jar
```

Nếu output cho biết một class **not found**, hãy cung cấp runtime dependency graph cần thiết:

```shell
jdeps --missing-deps \
  --class-path "dependencies/client-library.jar:dependencies/database-driver.jar" \
  build/libs/orders-app.jar
```

**Không xem việc thiếu class là một cảnh báo có thể bỏ qua mặc định.** Nó có thể làm phân tích thiếu đầy đủ hoặc gây `NoClassDefFoundError` trong một code path ít chạy.

### 6.1. `--ignore-missing-deps` có thể dùng lúc khảo sát, không để kết luận sạch

`jdeps` hỗ trợ `--ignore-missing-deps` ở một số chế độ phân tích. Nó có thể giúp **tiếp tục khảo sát** trong điều kiện thiếu dependencies, nhưng không có nghĩa dependencies đã đầy đủ. Một báo cáo dùng flag này phải ghi rõ rằng vẫn có **analysis gaps**.

Thực hiện scan cuối với full classpath/module path phù hợp và giữ danh sách những dependencies chưa resolve. Không “chữa” vấn đề bằng cách tự động thêm mọi JAR tìm thấy trên ổ đĩa mà không kiểm soát versions/nguồn gốc.

## 7. Dùng `jdeps` để nhìn module dependencies

Trong ứng dụng có `module-info.java` hoặc khi cần đóng gói custom runtime bằng `jlink`, các tùy chọn sau hữu ích:

```shell
# Liệt kê module dependencies có thể nhận diện được.
jdeps --list-deps build/libs/orders-app.jar

# Rút gọn các cạnh implied bởi requires transitive.
jdeps --list-reduced-deps build/libs/orders-app.jar

# In danh sách module dạng phân cách dấu phẩy.
jdeps --print-module-deps build/libs/orders-app.jar
```

`--print-module-deps` có thể cung cấp đầu vào để **nghiên cứu** `jlink --add-modules`. Đây là điểm khởi đầu, **không phải khẳng định custom image đã đủ mọi provider được tải động**, service binding, resource và native dependencies. Cần test startup và các code paths thực tế của packaged runtime.

### 7.1. Modular JAR và module path

Với modular artifacts, chuẩn bị module path phù hợp:

```shell
jdeps --module-path "mods:dependencies" --module com.example.orders
```

`com.example.orders` là **tên module minh họa** phải thay theo descriptor thật. `--module` chỉ phù hợp khi module đã được resolve từ module path và cấu hình đúng.

`jdeps --check com.example.orders` còn có thể giúp xem module graph/module descriptor và những qualified exports không được sử dụng theo hợp đồng công cụ. Nó **không thay thế** việc chạy ứng dụng để tìm lỗi deep reflection ở runtime.

### 7.2. Tạo `module-info.java` chỉ là bản nháp

`jdeps --generate-module-info output-dir some-library.jar` có thể tạo **module descriptor dự thảo**. Nó **ghi file** và có hạn chế khi kết hợp với một số options. Không sử dụng kết quả như một hợp đồng mô-đun hoàn chỉnh mà chưa review `exports`, `opens`, providers, reflection, native access và các consumers.

Với bài này, ưu tiên **đọc phụ thuộc và phân tích rủi ro**, không tự chỉnh sửa dependency module descriptors trong bước quét.

## 8. Multi-release JAR: chọn đúng version view

**Multi-release JAR** có thể chứa class files khác nhau được JVM chọn tùy runtime version, ví dụ các entries dưới `META-INF/versions/21` và `META-INF/versions/27`. Nếu chỉ quét view không đúng, kết quả có thể bỏ sót đường code thực sự chạy trên Java 27.

```shell
# Phân tích view Java 27 của multi-release JAR.
jdeps --multi-release 27 --jdk-internals build/libs/client-library.jar

# So sánh view phù hợp với runtime cũ khi cần.
jdeps --multi-release 21 --jdk-internals build/libs/client-library.jar
```

`--multi-release` nhận số phiên bản Java từ 9 trở lên hoặc `base`. Sự khác nhau giữa hai báo cáo cho biết **những class dependencies thay đổi theo release view**, không tự chứng minh code của mỗi view đã chạy qua mọi test.

### 8.1. Chú ý phiên bản bytecode

JDK 27 có thể đọc các class files của những phiên bản cũ được hỗ trợ, nhưng một JDK cũ không chạy được class file mới hơn khả năng của nó. Nếu sản phẩm cần **chạy trên nhiều bản JDK**, phải biên dịch với `--release` phù hợp và test trên **từng runtime mục tiêu**; chỉ chạy `jdeps` bằng JDK 27 không thay thế được kiểm thử tương thích ngược.

## 9. Giới hạn của `jdeps`: dependency tĩnh không phải khả năng chạy thật

`jdeps` dựa trên thông tin phụ thuộc có thể đọc từ class files. Những trường hợp sau có thể không được phản ánh đầy đủ:

- `Class.forName(classNameFromConfig)`, plugin discovery, phản chiếu chọn member theo tên.
- `ServiceLoader` và providers chỉ xuất hiện khi cấu hình hoặc runtime module resolution thỏa mãn.
- JNI, native libraries và các symbol/native dependencies bên ngoài JVM.
- Resources như `.properties`, TLS certificates, database drivers/configuration, scripts và serialization formats.
- Logic được sinh ra/thay đổi bằng bytecode instrumentation trong quá trình chạy.
- Tính đúng đắn của giao dịch và thay đổi semantics trong thư viện dù public API vẫn không đổi.

Ví dụ:

```java
String providerName = System.getProperty("app.provider");
Class<?> providerType = Class.forName(providerName);
```

Trong bytecode, có liên kết rõ đến `Class.forName`, nhưng **không nhất thiết có tham chiếu tĩnh** đến class thật do `providerName` chỉ định. Một báo cáo `jdeps` “không thấy JDK internals” vẫn cần kiểm thử theo **cấu hình thực tế**.

### 9.1. Không kết luận “mọi dependency đều là lỗi”

Phụ thuộc vào `java.sql`, `java.net.http` hoặc `java.xml` qua public API là bình thường nếu ứng dụng có nhu cầu. Điều đáng chú ý là:

1. **Không tìm thấy dependency** cần khi runtime chạy.
2. **Phụ thuộc internal/unsupported APIs**.
3. **Thành phần ngoài kiến trúc mong muốn**, ví dụ một thư viện nền tảng kéo thêm GUI module không cần thiết.
4. **Public API lộ implementation type** làm khó thay thế dependency.

Báo cáo nên phân biệt **inventory** với **finding cần xử lý**; không lập kế hoạch sửa chỉ vì công cụ in ra nhiều dòng.

## 10. `jdeprscan`: tìm Java SE deprecated APIs trong bytecode

`jdeprscan` (deprecated API elements scanner) quét `.class`, thư mục classes hoặc JAR để phát hiện **lời gọi/tham chiếu đến API Java SE đã deprecated**:

```shell
# Phân tích JAR đã được build.
jdeprscan build/libs/orders-app.jar

# Hoặc thư mục classes.
jdeprscan build/classes/java/main

# Chọn tập deprecations theo Java SE 27.
jdeprscan --release 27 build/libs/orders-app.jar
```

**Điểm quan trọng:** Nó **không** báo tất cả API deprecated của các third-party libraries. Ví dụ một method được annotation `@Deprecated` trong thư viện thanh toán tự viết có thể bị `javac` cảnh báo khi biên dịch nguồn gọi, nhưng `jdeprscan` **không có nghĩa vụ** đưa method đó vào báo cáo vì nó không thuộc Java SE.

### 10.1. Những gì `jdeprscan` không làm

- Không tìm lỗi cú pháp source hay unsupported language features.
- Không phát hiện một API đã **bị loại bỏ khỏi JDK** nếu không còn metadata cần thiết cho quét.
- Không thể hiện mọi rủi ro do **reflection**, JNI, runtime instrumentation hoặc cấu hình.
- Không xác nhận một thư viện bên ngoài đã tương thích về **hành vi** với Java 27.
- Không tự động chọn replacement API hay sửa mã.

Đối với code có source, nên **kết hợp `jdeprscan` và `javac -Xlint`**, không chọn một trong hai.

## 11. Tùy chọn `jdeprscan` quan trọng cho upgrade

| Tùy chọn | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `--release 27` | Quét dựa vào tập API deprecated theo Java SE 27 | Cần chạy công cụ từ **JDK có hỗ trợ release 27** |
| `--for-removal` | Chỉ hiện các API bị đánh dấu deprecated **for removal** | Không đồng nghĩa các API đó đã bị xóa |
| `--list` / `-l` | Liệt kê các API deprecated mà tool biết | **Không** truyền JAR/class để scan cùng `--list` |
| `--class-path PATH` | Cung cấp các classes phụ thuộc để resolve bytecode | Path phải phù hợp với runtime/build |
| `--verbose` | Thêm chi tiết khi phân tích | Dùng khi kết quả cần điều tra |
| `--help` | Xem cú pháp thật của executable | Giúp tránh dùng syntax cũ từ tài liệu phiên bản khác |

Quét riêng API dự kiến bị loại bỏ:

```shell
jdeprscan --release 27 --for-removal build/libs/orders-app.jar
```

Liệt kê tập metadata mà scanner hỗ trợ:

```shell
jdeprscan --release 27 --list
jdeprscan --release 27 --for-removal --list
```

**`--list` không phân tích artifact.** Kết quả liệt kê chỉ là tập APIs mà công cụ đang biết thuộc nhóm đó, **không** phải danh sách usages của dự án.

### 11.1. Chú ý sự khác nhau giữa tài liệu cũ và JDK đang chạy

Một số trang hướng dẫn/cú pháp được tái sử dụng từ các đời JDK trước có thể hiển thị danh sách `--release` quá cũ. Khi mục tiêu là Java 27, hãy chạy:

```shell
jdeprscan --help
```

Trên bản JDK 27 hỗ trợ tương ứng, `--release 27` là giá trị hợp lệ. Không mặc định `--release` luôn chấp nhận mọi phiên bản tương lai nếu tool hiện tại chưa hỗ trợ. Đồng thời, đừng lấy ví dụ Java 9 rồi áp đúng danh sách version hợp lệ của Java 9 vào Java 27.

### 11.2. `--release` chỉ thay đổi tập API deprecation được so

Một thư viện build bằng Java 17 có thể vẫn gọi API bị đánh dấu deprecated trong Java 27. Khi scan với tập Java SE 27, báo cáo cho biết **tình trạng API ở JDK mục tiêu**. Điều này khác với việc biên dịch lại source bằng `--release 17` hoặc chạy artifact trên JDK 17.

Nếu cần so sự thay đổi deprecation giữa hai thời điểm, có thể quét cùng một artifact với `--release` tương ứng mà bản tool hỗ trợ, rồi **so sánh tập findings**. Không nhầm chênh lệch báo cáo với thông báo rằng API đã chắc chắn bị xóa.

## 12. Classpath đầy đủ: điều kiện để `jdeprscan` có ích

`jdeprscan` cần nhìn thấy các classes mà artifact phụ thuộc để phân tích. Nếu thiếu, công cụ có thể báo:

```text
error: cannot find class ...
```

Khi gặp lỗi đó, không được kết luận “không phát hiện deprecation”. Hãy bổ sung classpath:

```shell
# Linux/macOS: dấu : phân tách các entries.
jdeprscan --release 27 \
  --class-path "dependencies/a.jar:dependencies/b.jar" \
  build/libs/orders-app.jar
```

Trên Windows, dùng dấu chấm phẩy:

```powershell
jdeprscan --release 27 --class-path "dependencies\a.jar;dependencies\b.jar" build\libs\orders-app.jar
```

**Không** trộn bừa `--module-path` của `jdeps` vào command `jdeprscan`: tài liệu `jdeprscan` không cung cấp cùng một tập tùy chọn với `jdeps`. Cần xem `jdeprscan --help` để có cú pháp supported và tạo classpath giải quyết dependencies phù hợp.

### 12.1. Quét dependencies riêng khi cần

Một ứng dụng có thể không trực tiếp gọi API deprecated, nhưng JAR thư viện lại gọi. Để inventory phạm vi:

```shell
jdeprscan --release 27 dependencies/a.jar
jdeprscan --release 27 dependencies/b.jar
```

Những command này giả định đầy đủ các dependencies được cung cấp hoặc package đã tự chứa những classes được tham chiếu. Với hàng trăm artifacts, tự động hóa vòng lặp từ danh sách dependencies của build system, **không phải** bỏ qua bất kỳ lỗi resolve nào để nhận một báo cáo có vẻ sạch.

Đừng nhầm output của thư viện vendor với lỗi buộc ứng dụng phải sửa một dòng source. Với dependency không sở hữu, hướng đi thường là **nâng phiên bản**, thay thế hoặc làm việc với nhà cung cấp, kèm regression tests.

### 12.2. Phạm vi API Java SE khác JDK internal API

`jdeprscan` chỉ tập trung vào **deprecation của Java SE APIs**. Một internal JDK API có thể không được `jdeprscan` liệt kê dù rất rủi ro; vì thế phải chạy `jdeps --jdk-internals` riêng.

Ngược lại, một public Java SE API đã deprecated vẫn có thể hiện trong `jdeprscan` ngay cả khi `jdeps --jdk-internals` không tìm thấy gì, bởi **“deprecated” và “internal” không phải cùng thuộc tính**.

## 13. Giải mã output `jdeprscan`

Output có thể hiển thị tên class theo **JVM internal form** (dấu `/`), tên method, tham số và return type dưới dạng **method descriptor**.

Ví dụ dạng minh họa:

```text
class example/LegacyConsumer uses deprecated method java/util/Date::getYear()I
```

Cách đọc:

- `example/LegacyConsumer`: class **đang dùng** API.
- `java/util/Date`: class của Java SE cung cấp API deprecated.
- `getYear`: tên method.
- `()I`: không có tham số, trả về kiểu primitive `int`.

Một số ký hiệu của JVM descriptor:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `I` | `int` |
| `J` | `long` |
| `Z` | `boolean` |
| `D` | `double` |
| `V` | `void` |
| `Ljava/lang/String;` | Tham chiếu `java.lang.String` |
| `[I` | Mảng `int[]` |
| `(Ljava/lang/String;)V` | Method nhận `String`, trả `void` |
| `<init>` | Tên đặc biệt của constructor trong class file |
| `<clinit>` | Class initialization method |

Sử dụng **tên class và signature** để xác định đúng call site và replacement, đặc biệt khi có method overloads. Không suy từ một tên method trùng nhau rằng mọi overload đều đã deprecated.

### 13.1. Vị trí code cần sửa có thể không còn trong source

`jdeprscan` đọc bytecode nên có thể thấy usages trong:

- JAR đã được publish của một dependency.
- Class files generated từ annotation processor.
- Artifact được build từ một nhánh/tag cũ nhưng source hiện tại đã đổi.

Trong những tình huống này, cần truy ngược từ **tên class** về artifact owner và source của đúng version. Không sửa mã mới vô can chỉ vì tên method tương tự.

## 14. Vì sao `javac -Xlint` là lớp cảnh báo không thể thiếu?

`jdeps`/`jdeprscan` yêu cầu bytecode đã tồn tại. Nhưng developer thường cần phát hiện vấn đề **ngay khi biên dịch source**, trước khi tạo artifact mới.

`javac` cung cấp những lựa chọn:

```shell
# Chỉ bật các nhóm cảnh báo trọng tâm cho migration.
javac -Xlint:deprecation,removal,unchecked,rawtypes \
  --release 27 -d out src/MigrationProbe.java
```

Command trên giả định tồn tại file đầu vào, thư mục output có thể ghi và tất cả source/dependencies đã được cung cấp. Nếu mã có nhiều files hoặc packages, compile qua build tool hoặc liệt kê đúng source set/classpath.

Các nhóm cảnh báo:

| Cờ `-Xlint` | Phát hiện loại rủi ro |
| --- | --- |
| `deprecation` | Tham chiếu/override những phần tử đã deprecated |
| `removal` | Dùng API được đánh dấu **for removal** |
| `unchecked` | Unchecked conversions/casts/operations do generics/type erasure |
| `rawtypes` | Dùng raw generic types |
| `preview` | Cảnh báo liên quan đến preview language features khi áp dụng |
| `module` | Một số vấn đề liên quan module declarations/access |
| `processing` | Những vấn đề liên quan annotation processing |
| `serial` | Cảnh báo liên quan `Serializable` và serial version |
| `try` | Một số vấn đề trong try/try-with-resources |

**Không phải mọi category đều mặc định bật.** Trong `javac` Java 27, các categories mặc định có `removal` và `preview`, nhưng không phải tất cả như `deprecation` hay `unchecked`. Bật rõ những gì cần kiểm tra giúp build log đầy đủ và lặp lại được.

### 14.1. `-Xlint` và `-deprecation`

`-deprecation` là một dạng rút gọn cho `-Xlint:deprecation`. Có thể dùng:

```shell
javac -deprecation -d out src/MigrationProbe.java
```

Không cần chỉ dùng đúng `-deprecation` nếu dự án còn muốn kiểm tra `removal`, `unchecked` hoặc các categories khác.

### 14.2. `-Xlint:all`

```shell
javac -Xlint:all --release 27 -d out src/MigrationProbe.java
```

`-Xlint:all` bật toàn bộ warning categories được JDK đó hỗ trợ, giúp xem phạm vi rộng hơn. Nhưng điều đó cũng có thể làm output nhiều và có warnings không trực tiếp liên quan migration. Trong CI, cần phân loại để **không bị cảnh báo quan trọng chìm giữa hàng nghìn dòng noise**.

### 14.3. Lưu ý warning không đồng nghĩa lỗi chạy

Một cảnh báo `unchecked` cho biết compiler không thể chứng minh tính an toàn của một phép chuyển kiểu, **không** khẳng định mọi lần chạy sẽ ném `ClassCastException`. Nhưng nó vẫn là rủi ro cần đánh giá, nhất là ở ranh giới generics và reflection.

Tương tự, warning `deprecation` không nói API đã bị xóa trong Java 27; nó cho biết cần xem xét hợp đồng và phương án thay thế.

## 15. `-Werror` và `-Werror:removal`: khi nào biến warning thành lỗi build?

Khi một nhóm đã xử lý các warnings quan trọng và muốn **ngăn tái xuất hiện**, có thể cấu hình compiler fail build nếu warning xuất hiện:

```shell
# Nghiêm ngặt: mọi compiler warnings đều làm compilation fail.
javac -Xlint:deprecation,removal,unchecked,rawtypes \
  -Werror --release 27 -d out src/MigrationProbe.java
```

Trong Java 27, `javac` còn hỗ trợ **`-Werror:removal`** để chỉ những warnings thuộc category `removal` trở thành lỗi:

```shell
# Chặn riêng việc dùng API marked for removal.
javac -Xlint:deprecation,removal,unchecked \
  -Werror:removal --release 27 -d out src/MigrationProbe.java
```

`-Werror` không phải phép tự sửa mã. Nó chỉ làm compilation thất bại khi có warning thuộc phạm vi đã chọn. Không thêm ngay vào một codebase cũ có hàng nghìn warnings rồi coi mọi modules chưa build được là nhiệm vụ không thể hoàn thành.

### 15.1. Lộ trình siết cảnh báo theo giai đoạn

1. **Quan sát:** bật `-Xlint`, thu báo cáo và phân loại findings.
2. **Ưu tiên P0/P1:** giải quyết API for removal, internals và compiler errors trước.
3. **Chặn hồi quy:** bật `-Werror:removal` cho source sets/modules đã sạch.
4. **Mở rộng:** chặn `deprecation`, `unchecked` hoặc toàn bộ warnings khi đã có baseline sạch và quy trình exceptions.
5. **Duy trì:** review warnings mới trong pull requests, không để tăng dần qua mỗi release.

Đảm bảo warnings từ **annotation processors/generated source** được quy về đúng owner; không tắt toàn bộ warnings chỉ để che một số findings đến từ mã generated mà chưa có kế hoạch nâng processor.

### 15.2. Warning vẫn có thể bị suppression hoặc nằm trong binary

`@SuppressWarnings` và các tùy chọn compiler có thể làm một số warnings không xuất hiện; `-Werror` chỉ xử lý **những warnings được compiler phát ra**. Thêm vào đó, một JAR đã được biên dịch trước đó **không được javac tái kiểm tra source** chỉ vì app của bạn dùng `-Werror`.

Đây là lý do cần kết hợp compile warnings với **`jdeprscan` trên artifacts**, `jdeps` trên dependencies và chính sách quản lý suppression.

## 16. `--release`: kiểm tra ngôn ngữ, API và class-file target

`--release N` khiến `javac` sử dụng các quy tắc ngôn ngữ và tập API công bố phù hợp Java release `N`, đồng thời tạo class files nhắm tới release đó.

```shell
# Ứng dụng được nâng và chỉ yêu cầu Java 27.
javac --release 27 -d out src/MigrationProbe.java

# Thư viện vẫn phải chạy trên Java 21 và Java 27.
javac --release 21 -d out src/PortableLibrary.java
```

Hai lệnh là **những mục tiêu build khác nhau**; người học phải thay filenames theo dự án. Nếu dùng API Java 27 chưa tồn tại ở Java 21, lệnh thứ hai sẽ không compile. Đây là tính năng quan trọng khi một thư viện cần **backward compatibility**, thay vì chỉ kiểm tra chạy được trên máy developer có JDK mới.

### 16.1. Vì sao không chỉ dùng `-source` và `-target`?

`--source` kiểm soát ngôn ngữ, `--target` kiểm soát phiên bản class files; riêng cặp này **không đủ để bảo đảm** code không vô tình tham chiếu API chỉ tồn tại trong JDK compiler hiện tại.

`--release` xử lý cả **source/API target** và bytecode target, là lựa chọn phù hợp cho build cần chạy trên bản Java đích. Nó **không thể kết hợp đồng thời** với `-source` hoặc `-target` trong cùng invocation.

### 16.2. `--release 21` và scan theo Java SE 27 vẫn có ý nghĩa khác nhau

Giả sử thư viện phải chạy trên cả Java 21 và 27:

- Build với `javac --release 21` để giữ ngôn ngữ/API/bytecode tương thích với 21.
- Chạy `jdeprscan --release 27` trên artifact đó để xem những **Java SE APIs sẽ bị đánh dấu deprecated theo JDK 27**.
- Test artifact trên **cả JDK 21 và JDK 27**.

Không có một lệnh duy nhất thay thế đủ ba phép kiểm tra.

### 16.3. Preview features là hợp đồng khác

Không đưa `--enable-preview` vào build migration chỉ để làm compiler chấp nhận source không biên dịch được. Preview features yêu cầu compiler/runtime flags thích hợp và có thể thay đổi trong các JDK sau. Với sản phẩm cần tương thích bền vững, chỉ dùng preview khi đã có chính sách thử nghiệm, kiểm thử và kế hoạch migration rõ ràng.

## 17. `@SuppressWarnings`: đừng biến báo cáo sạch thành ảo giác

Java hỗ trợ suppression có mục đích:

```java
@SuppressWarnings("unchecked")
static <T> T castFromTrustedBoundary(Object raw, Class<T> type) {
    return type.cast(raw);
}
```

Ví dụ trên **thực tế không cần** `@SuppressWarnings("unchecked")` vì `Class.cast` được kiểm tra runtime; annotation chỉ minh họa rằng có thể che một category. Trong code mới, **hãy xóa suppression không cần thiết**.

Một suppression hợp lý cần:

- Được đặt ở **phạm vi nhỏ nhất** chứa cảnh báo.
- Có **lý do cụ thể** và test bảo vệ giả định an toàn.
- Có **issue/owner và thời hạn** nếu đang chấp nhận tạm rủi ro migration.
- Không sử dụng thay vì sửa một API deprecated/for-removal đã có replacement.

Không nên cấu hình `-Xlint:none` cho toàn bộ dự án chỉ để CI không hiện cảnh báo. Nó làm mất tín hiệu cho các lần nâng cấp tiếp theo.

### 17.1. `@Deprecated` trên chính mã của mình cũng cần lộ trình

Trong một API tự định nghĩa:

```java
public final class CatalogApi {
    @Deprecated(since = "2.0", forRemoval = true)
    public static String oldCode(String text) {
        return text.strip();
    }

    public static String normalizeCode(String text) {
        return text.strip();
    }
}
```

Compiler có thể cảnh báo ở source sử dụng `oldCode` trong class khác. **`jdeprscan` sẽ không báo `CatalogApi.oldCode`**, vì đó không phải API Java SE. Để quản lý lifecycle cho API nội bộ hoặc third-party, cần compiler warnings, binary/source scanners phù hợp và tài liệu release riêng của thư viện.

**`forRemoval=true` không buộc bạn xóa API ngay.** Nhưng nó làm rõ ý định và giúp callers được cảnh báo sớm hơn; người duy trì phải công bố replacement và thực hiện versioning tương thích.

## 18. Ví dụ end-to-end: tạo một finding có thể giải thích được

Ví dụ này có **hai file Java** độc lập. Chúng cố tình dùng một API Java SE deprecated và một API tự định nghĩa marked for removal để minh họa sự khác biệt giữa `javac` và `jdeprscan`. **Đây không phải mã nên viết mới trong production.**

### 18.1. `LegacyApi.java` — API của dự án đang chuyển đổi

```java
public final class LegacyApi {
    private LegacyApi() {}

    @Deprecated(since = "1.0", forRemoval = true)
    public static String oldNormalize(String input) {
        return input.strip();
    }

    public static String normalize(String input) {
        return input.strip();
    }
}
```

### 18.2. `MigrationProbe.java` — caller cũ cần sửa

```java
import java.util.Date;

public class MigrationProbe {
    public static void main(String[] args) {
        // API Java SE deprecated, chỉ dùng để minh họa finding.
        int legacyYear = new Date(0L).getYear();

        // API ứng dụng đã marked for removal.
        String code = LegacyApi.oldNormalize("  ORD-001  ");

        System.out.println("old year field = " + legacyYear);
        System.out.println("code = " + code);
    }
}
```

`Date.getYear()` là **API Java SE đã deprecated**, có semantics kiểu năm trừ 1900 và dùng local timezone. Nó không phải cách lấy năm lịch trong code mới. `LegacyApi.oldNormalize()` là **API custom** và được đánh dấu `forRemoval=true`.

### 18.3. Biên dịch và đọc warnings

Đặt hai file trong cùng một thư mục demo không có `package` rồi chạy:

```shell
javac --release 27 \
  -Xlint:deprecation,removal \
  -d out \
  LegacyApi.java MigrationProbe.java
```

Trên JDK 27, dự kiến nhận **warning** về `Date.getYear()` và về `LegacyApi.oldNormalize()`. Category/wording chính xác phụ thuộc JDK output; thông thường có:

```text
warning: [deprecation] getYear() in Date has been deprecated
warning: [removal] oldNormalize(String) in LegacyApi
         has been deprecated and marked for removal
```

Đây là **đầu ra rút gọn minh họa**, không phải log đã chạy hoặc xác nhận số dòng warning. Không dùng `-Werror:removal` ở bước đầu nếu mục tiêu là **thu thập** warnings: cờ đó cố ý biến warning thứ hai thành compile failure.

### 18.4. Quét bytecode sau compile

```shell
jdeps -summary out
jdeps --jdk-internals out
jdeprscan --release 27 out
jdeprscan --release 27 --for-removal out
```

Diễn giải đúng:

- `jdeps -summary out` cho biết dependencies có thể nhận diện, thường có `java.base`.
- `jdeps --jdk-internals out` **không bắt buộc có finding**, vì ví dụ dùng public Java SE API chứ không dùng JDK internals.
- `jdeprscan --release 27 out` có thể tìm lời gọi **`Date.getYear()`**.
- `jdeprscan --release 27 --for-removal out` **không phải** cách liệt kê mọi API custom `forRemoval=true`. Nó chỉ tập trung các API Java SE có trạng thái tương ứng.

Nếu `jdeprscan` không resolve được dependency nào đó, phải xem lỗi classpath thay vì tin kết quả quét là đầy đủ.

### 18.5. Sửa source bằng public API hiện hành

Chuyển code về:

```java
import java.time.Instant;
import java.time.ZoneId;

public class MigrationProbe {
    public static void main(String[] args) {
        // Chọn timezone theo hợp đồng ứng dụng.
        int calendarYear = Instant.ofEpochMilli(0L)
                .atZone(ZoneId.systemDefault())
                .getYear();

        String code = LegacyApi.normalize("  ORD-001  ");

        System.out.println("calendar year = " + calendarYear);
        System.out.println("code = " + code);
    }
}
```

Mã thay thế dùng **`java.time`** và API custom `normalize` còn được hỗ trợ. Lưu ý `Date.getYear()` trả **năm trừ 1900**, còn `ZonedDateTime.getYear()` trả **năm dương lịch đầy đủ**; đó là **thay đổi semantics có chủ đích**, không phải phép thay thế giữ nguyên mọi giá trị số. Khi nâng cấp thật phải xác định hợp đồng dữ liệu đầu ra và timezone trước khi thay.

Chạy lại:

```shell
javac --release 27 -Xlint:deprecation,removal -Werror:removal \
  -d out LegacyApi.java MigrationProbe.java

jdeprscan --release 27 out
```

Nếu không còn lời gọi deprecated trong những class files được quét, `jdeprscan` có thể không in finding tương ứng. Nếu artifact `out` còn các class files **cũ** từ lần compile khác, kết quả có thể bị nhiễm; phải dùng output sạch/cách ly cho mỗi build.

**Hạn chế ví dụ:** không có JUnit hoặc regression tests; code chỉ minh họa cơ chế phát hiện. Một dự án thực tế cần thêm tests bảo đảm logic đổi sang `java.time` đúng timezone/business semantics.

## 19. Đưa warnings vào Gradle mà không phụ thuộc thao tác thủ công

Trong dự án dùng Gradle với Kotlin DSL, có thể cấu hình compiler tasks để những warnings quan trọng xuất hiện nhất quán ở developer/CI:

```kotlin
// Ví dụ trong build.gradle.kts.
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:deprecation,removal,unchecked,rawtypes"
        )
    )
}
```

`JavaCompile` ở đây là task type của Gradle Java plugin. Java toolchain giúp xác định JDK compiler; `options.release` chọn release target. Nếu một thư viện còn cam kết hỗ trợ Java 21, **không** đặt `release=27` chỉ vì môi trường CI dùng JDK 27; cần giữ target thấp phù hợp.

### 19.1. Khi đã sạch warnings marked for removal

Có thể thêm:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Werror:removal")
}
```

Đây là cấu hình **bổ sung**, không phải một file Gradle hoàn chỉnh. Trước khi bật, xác minh Gradle, Kotlin DSL plugin, Java toolchain và annotation processors thực tế tương thích JDK 27. `-Werror:removal` thuộc compiler JDK 27; nếu build còn dùng compiler JDK cũ không hỗ trợ cú pháp đó, phải điều chỉnh chiến lược phù hợp.

### 19.2. Warnings của `main` và `test`

`tasks.withType<JavaCompile>()` có thể cấu hình nhiều source sets, bao gồm `main` và `test`. Test code cũng có thể còn gọi deprecated APIs hoặc dùng unchecked casts. Tuy nhiên, áp chính sách build fail cho tests có third-party test framework cũ có thể dẫn tới khối lượng remediation riêng; hãy lên kế hoạch thay dependencies/testing libraries trước khi siết toàn bộ.

Không dùng một thao tác `./gradlew clean build` để chỉ “quét” mà bỏ qua việc nó có thể chạy processors, tests hoặc nhiệm vụ ghi output theo cấu hình dự án. Trong quy trình thực tế, CI owner chọn các tasks cần chạy và cô lập artifacts; trong bài viết này chỉ mô tả cấu hình.

## 20. Cấu hình Maven Compiler Plugin cho migration

Với Maven, cấu hình compiler theo mục tiêu chạy trên Java 27:

```xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>27</release>
                <compilerArgs>
                    <arg>-Xlint:deprecation,removal,unchecked,rawtypes</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **mảnh cấu hình `pom.xml`**, không phải file Maven đầy đủ và không phải tuyên bố plugin version 3.14.1 là bản mới nhất. Sử dụng phiên bản được tổ chức kiểm chứng với toolchain và build setup, đồng thời có dependency management thích hợp.

Khi đã sửa những API for removal và muốn fail build do hồi quy:

```xml
<compilerArgs>
    <arg>-Xlint:deprecation,removal,unchecked,rawtypes</arg>
    <arg>-Werror:removal</arg>
</compilerArgs>
```

### 20.1. Không sao chép `release=27` vào một thư viện cần Java thấp hơn

Maven compiler có thể chạy dưới JDK 27 nhưng vẫn tạo artifact cho Java 21 bằng `<release>21</release>` khi release được compiler hỗ trợ. Cần test artifact trên JDK 21 thật để bảo đảm runtime compatibility.

Với mã modular, reflection hoặc annotation processing, cấu hình compiler/path phải tương ứng với source sets/module boundaries thực tế. Các commands của `jdeps`/`jdeprscan` là **bước phân tích artifact bổ sung**, không tự động xuất hiện chỉ vì Maven compiler bật `-Xlint`.

## 21. Đọc findings theo owner và mức độ ưu tiên

Một báo cáo nâng cấp có giá trị khi chuyển thành **danh sách công việc có thể xử lý**, không chỉ lưu log dài.

Mẫu bảng triage:

| Artifact/class | Công cụ | Loại finding | Owner | Hành động |
| --- | --- | --- | --- | --- |
| `app.jar / LegacyCodec` | `jdeps --jdk-internals` | JDK internal dependency | Application team | Thay public API hoặc nâng dependency |
| `app.jar / LegacyConsumer` | `jdeprscan` | Java SE deprecated method | Application team | Sửa code và regression test |
| `lib/payment-sdk.jar` | `jdeprscan --for-removal` | Java SE API for removal | Vendor/dependency team | Nâng SDK, theo dõi thời hạn |
| `app.jar / FileExporter` | `javac -Xlint:unchecked` | Unchecked conversion | Application team | Dùng generics/type validation |
| `app.jar` | `jdeps --missing-deps` | Dependency missing | Build/release team | Sửa packaging/resolution |
| `test plugin` | Runtime smoke test | Deep reflection blocked | Framework team | Nâng framework hoặc cấu hình mở package có kiểm soát |

Đây là **các loại finding giả định**, không phải kết quả quét workspace hiện tại. Cần lưu thêm source location, dependency version, JDK build, severity, remediation PR và trạng thái test.

### 21.1. Nhóm ưu tiên gợi ý

- **P0 – Không thể chạy/build hoặc rủi ro bảo mật trực tiếp:** class/method đã bị removed, missing dependency critical, module resolution failure, third-party driver không thể hoạt động.
- **P1 – Có khả năng bị chặn trong release tương lai hoặc không có hợp đồng ổn định:** Java SE `forRemoval=true`, JDK internal API, illegal deep reflection và runtime flags tạm.
- **P2 – Deprecated nhưng chưa có lịch removal rõ:** có replacement đã được hỗ trợ; cần kế hoạch migration và regression tests.
- **P3 – Cảnh báo chất lượng bổ sung:** unchecked/rawtypes/suppression không có căn cứ hoặc code chưa chuẩn hóa, xử lý theo ownership và rủi ro.

Mức độ **không phải luật cố định**. Ví dụ một deprecated API đang gây lỗi bảo mật có thể là P0; một internal API chỉ có trong thư viện dev-only ít rủi ro hơn internal API nằm trên critical production path.

### 21.2. Tách findings mới và tồn đọng

Trong codebase lớn:

1. Lưu **baseline report** có ghi timestamp, JDK build và artifact checksum.
2. Cho phép một số findings cũ có issue/owner và thời hạn được giải quyết.
3. **Không chấp nhận findings mới** ở nhóm rủi ro đã được khóa policy.
4. Giảm baseline qua từng iteration thay vì phải xử lý tất cả ở một commit.

Không tạo “baseline sạch” bằng cách xóa báo cáo lỗi resolve hoặc bỏ đi mọi dòng deprecation không phân loại.

## 22. Strong encapsulation và reflection: khoảng trống giữa các công cụ

Java Platform Module System áp dụng ranh giới **module readability, exports và opens**. Những vấn đề nâng cấp có thể phát sinh khi framework/test library muốn truy cập private field hoặc method bằng reflection.

Ví dụ runtime có thể báo:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible: module ... does not "opens ..."
```

`jdeps --jdk-internals` có ích với static references, nhưng **không đảm bảo** phát hiện mọi trường hợp reflection từ tên class/method được dựng động. `jdeprscan` cũng không kiểm tra quyền mở module, còn `javac` chỉ nhìn thấy một phần vấn đề access ở compile time.

### 22.1. Phân biệt `exports` và `opens`

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.model to com.example.serializer;
}
```

- `exports` cho phép truy cập **public types/members** từ module đọc tương ứng theo các quy tắc Java.
- `opens` cho phép **deep reflection** vào package ở runtime theo scope đã khai báo.
- Hai mục đích khác nhau; không giải quyết nhu cầu deep reflection chỉ bằng `exports`.
- Nếu `com.example.serializer` chưa được resolve hoặc không đúng module name, cấu hình thực tế cần được kiểm tra.

`--add-opens` và `--add-exports` trên command line có thể hữu ích khi **chẩn đoán hoặc chuyển tiếp** ở một hệ thống legacy, nhưng không nên tồn tại vô thời hạn chỉ vì “cho chạy”. Ưu tiên nâng framework/driver/serialization library và dùng public APIs/JPMS declarations phù hợp.

### 22.2. Một external library chưa hỗ trợ Java 27

Nếu thư viện bị build bằng bytecode version cũ, nó **không tự động bất tương thích** với Java 27. Nhưng thư viện có thể chứa code reflection vào nội bộ JDK, dùng agent/native integration hoặc gọi API đã removed.

Vì thế:

1. Xem **release notes** và phiên bản Java hỗ trợ từ nhà cung cấp.
2. Quét artifact với `jdeps`/`jdeprscan` trong phạm vi có dependencies.
3. Chạy các **code paths thực tế** của thư viện trên JDK 27.
4. Nâng lên phiên bản hỗ trợ hoặc có kế hoạch thay thế.

Không đổi thư viện chỉ vì “nó được build bằng Java 8”; quyết định phải dựa trên năng lực thực tế và hỗ trợ của vendor.

## 23. Những loại thay đổi ngoài phạm vi ba công cụ

Khi nâng cấp JDK, có thể phải xem thêm:

| Loại thay đổi | Vì sao ba công cụ không đủ | Cách xác minh |
| --- | --- | --- |
| **TLS/certificates** | Truststore, providers và ciphers có thể thay đổi | Integration test kết nối thật, kiểm tra TLS configuration |
| **Serialization** | Binary compatibility không chứng minh data format và schema đúng | Test đọc/ghi dữ liệu cũ |
| **Time zone / locale** | TZDB và định dạng có thể đổi ngoài source | Test nghiệp vụ với fixed clock/timezones |
| **Reflection/plugin loading** | Tham chiếu class bằng `String`, service config | Runtime startup và plugin discovery test |
| **Native/JNI/FFM** | Liên quan native binaries, ABI, quyền/native access | Kiểm tra vendor support và chạy trên OS/arch mục tiêu |
| **Agents/profilers/instrumentation** | Tác động runtime/class loading không hiện đầy đủ trong bytecode ứng dụng | Test cùng agent và flags production |
| **Performance/GC** | Một ứng dụng đúng API vẫn có thể đổi latency/throughput | Performance baseline + load test |
| **Removed JVM launch flags** | Compiler/scanners không chạy command-line runtime production | Kiểm tra actual launch flags với Java 27 |
| **Service configuration** | Runtime image có thể thiếu tài nguyên/provider | Smoke test deploy image thật |

Nên đọc **JDK 27 Migration Guide** cho những thay đổi phiên bản/flags liên quan, đồng thời theo dõi các dependencies và sự khác nhau giữa JDK distribution thực tế.

## 24. CI pipeline gợi ý cho dự án Java 27

Một pipeline phân tích cần tách **compile source** và **scan artifact sau compile**:

```text
1. Resolve exact JDK 27 + dependency versions
                   |
2. Compile with --release target + -Xlint
                   |
3. Package deployable artifact / collect classpath
                   |
      +------------+----------------+
      |            |                |
      v            v                v
4a. jdeps      4b. jdeprscan    4c. dependency
   internals       deprecated       vendor audit
   missing deps    for-removal
      |            |                |
      +------------+----------------+
                   |
5. Normalize findings + decide CI gates
                   |
6. Unit/integration/smoke/security tests
                   |
7. Archive evidence and compare baseline
                   |
8. Release approval / canary / rollback plan
```

### 24.1. Những gì cần lưu lại

- JDK vendor, version và build ID.
- Artifact name/version/hash, source commit, build tool versions.
- Dependency graph và đường dẫn classpath/module path đã dùng.
- Lệnh thực hiện, stdout/stderr và exit status từ `javac`, `jdeps`, `jdeprscan`.
- Những lỗi `cannot find class` hoặc `missing-deps` chưa xử lý.
- Danh sách findings đã phân loại theo **owner, severity và phương án sửa**.
- Kết quả regression/integration tests và thời điểm chạy trên JDK 27.

**Không giả định exit code bằng 0 từ một lệnh scan nghĩa là “không có finding cần sửa”.** Nhiều scanner có thể chạy thành công và **in các phát hiện** mà không xem đó là lỗi thực thi tool. Cổng CI nên dựa trên reports đã phân loại và kiểm tra scan completeness, không chỉ dựa vào exit code.

### 24.2. Khi nào dùng `-Werror` trong CI?

Sau khi đã ổn định baseline, có thể chặn việc **bổ sung call sites mới** tới API for removal trong source. Nhưng với dependencies đã compile, `-Werror` không thay thế được `jdeprscan`. Với runtime behavior và reflection, cả hai đều không thay thế smoke/integration tests.

Không cho cảnh báo “có API deprecated trong thư viện vendor” tự động trở thành lý do **tắt compiler checks cho toàn bộ source**. Mỗi loại finding cần owner và cách xử lý riêng.

## 25. Gặp lỗi khi chạy công cụ: bảng chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Điều cần kiểm tra |
| --- | --- | --- |
| Shell báo `jdeps: command not found` | Đang dùng runtime tối giản, PATH không chứa JDK `bin` | Kiểm tra JDK installation và `JAVA_HOME` |
| `jdeprscan` không nhận `--release 27` | Executable đang chạy thuộc JDK cũ hoặc phiên bản công cụ khác | `jdeprscan --version`, `jdeprscan --help` |
| `jdeps` báo missing dependency | Classpath/module path không đầy đủ, artifact thiếu JAR | Resolve runtime dependency graph đúng version |
| `jdeprscan` báo `cannot find class` | Thiếu classes dùng để resolve input | Bổ sung `--class-path`, không bỏ warning |
| `jdeps --jdk-internals` không in findings | Có thể không có static references tới internal API, **hoặc có dynamic access** | Smoke tests, reflection/native review |
| `jdeprscan` không thấy custom `@Deprecated` của thư viện | Công cụ chỉ quét deprecated **Java SE** APIs | Dùng `javac -Xlint:deprecation`, inventory thư viện |
| `javac` fail với `--release 21` dù chạy JDK 27 | Dùng API hoặc cú pháp không có trong Java 21 | Chọn target đúng hợp đồng; sửa source |
| `javac -Werror` làm nhiều modules thất bại | Baseline warnings chưa được xử lý | Triage, staged gates và owner rõ ràng |
| Error `UnsupportedClassVersionError` ở runtime cũ | Class files được compile cho JDK mới hơn runtime | Dùng `--release` phù hợp và test runtime cũ |
| `InaccessibleObjectException` khi chạy | Framework/reflection bị strong encapsulation chặn | Nâng library, điều chỉnh `opens` có kiểm soát |
| `NoClassDefFoundError` dù `jdeps` không thấy vấn đề | Class được nạp động, classpath khác giữa scan và runtime | So runtime artifact, service configuration, loader |
| Warning biến mất sau `@SuppressWarnings` | Chỉ tắt cảnh báo, chưa loại rủi ro | Review từng suppression và regression tests |
| Scan JAR không phản ánh runtime Java 27 | Đang chọn sai `--multi-release` view, artifact stale | Dùng artifact mới, chọn đúng release view |
| JAR là executable/fat JAR đặc thù | Nested archives có thể không được công cụ duyệt như classpath chạy thực | Extract/chuẩn bị input an toàn theo packaging, quét artifacts riêng |

**Không ngắt mọi phân tích ngay khi có một warning:** hãy lưu các findings có thể đọc được, đồng thời đánh dấu **độ đầy đủ** của lần scan. Một báo cáo có lỗi resolve là **chưa hoàn tất**, không phải “zero findings”.

### 25.1. Không trộn output của JDK khác nhau

Nếu `java` chạy bằng JDK 27 nhưng `jdeps` từ JDK 21 được tìm thấy trước trong PATH, báo cáo có thể sử dụng tập platform modules và capabilities không khớp JDK đích. Trong CI hãy pin **tuyệt đối phiên bản công cụ** thông qua toolchain/container image đã quản trị.

### 25.2. Không mất thời gian sửa “false positive” khi chưa đọc contract

Một API deprecated có thể vẫn cần duy trì tạm thời vì yêu cầu tương thích của khách hàng. Trước khi sửa:

1. Đọc Javadoc/`@Deprecated` và lời khuyên thay thế.
2. Kiểm tra semantics cũ và mới, kể cả timezone, charset, concurrency, exception behavior.
3. Xem các callers, serialized data và giao thức công khai.
4. Tạo regression tests cho tình huống đặc biệt trước khi thay implementation.

Không thay `Date.getYear()` bằng `LocalDate.now().getYear()` một cách máy móc nếu chương trình đang xử lý **timestamp trong dữ liệu lịch sử**; phải chuyển đúng thời điểm và múi giờ như ví dụ mục 18.

## 26. Quy trình nâng cấp theo đợt: từ baseline tới rollout Java 27

Một dự án có nhiều services và thư viện không nhất thiết nên chuyển tất cả cùng một lúc:

### Giai đoạn A — Inventory và phạm vi

Xác định:

- JDK source/target/runtime đang dùng ở local, CI, container và production.
- Nhóm thư viện quan trọng: framework, JDBC drivers, agents, serializers, security providers.
- Artifacts thực sự deploy, kể cả plugins, shaded JARs và các JAR tải động.
- Các flags/module overrides đang dùng để mở quyền truy cập.

### Giai đoạn B — Static analysis và build

1. Build lại source bằng JDK 27, giữ `--release` theo cam kết runtime.
2. Bật `-Xlint:deprecation,removal,unchecked,rawtypes`.
3. Quét JAR/class outputs bằng `jdeps --jdk-internals` và `--missing-deps`.
4. Quét Java SE deprecated usages bằng `jdeprscan --release 27`, sau đó lọc `--for-removal`.
5. Quét dependencies ngoài JDK theo release notes và advisory sources phù hợp.

### Giai đoạn C — Remediation

Ưu tiên **unblock build/runtime**, rồi xử lý những API for-removal, internals và thư viện không còn hỗ trợ, sau đó giảm warnings còn lại. Mỗi thay đổi có regression tests. Nếu cần workaround module tạm, ghi lý do, owner và mục tiêu loại bỏ.

### Giai đoạn D — Runtime verification

- Unit tests và integration tests trên Java 27.
- Startup/smoke tests trong **đúng runtime image** được phát hành.
- Kiểm tra external services, DB, TLS, reflection và native agents.
- So baseline hiệu năng, GC, memory và latency.

### Giai đoạn E — Canary và rollback

Triển khai một phần lưu lượng, giám sát SLO/errors cùng metric JVM, bảo đảm có cách rollback artifact/runtime phù hợp và không phá khả năng đọc dữ liệu/serialization khi chuyển đổi.

Sau khi triển khai, tiếp tục theo dõi deprecations trong **các bản cập nhật dependencies**. Kết thúc một lần upgrade không có nghĩa không bao giờ xuất hiện API for-removal mới.

## 27. Những anti-pattern khi dùng công cụ migration

| Cách làm sai | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Chạy `jdeps` trực tiếp trên `.java` | `jdeps` phân tích bytecode | Build classes/JAR trước |
| Quét mỗi JAR ứng dụng rồi coi toàn dependency tree sạch | Library JAR khác có thể dùng internals/deprecated | Quét dependencies quan trọng và transitive scope |
| Dùng `jdeprscan` để tìm tất cả third-party `@Deprecated` | Chỉ Java SE API deprecations | Compiler warnings và nguồn riêng cho third-party |
| Dùng `--list` rồi tưởng đó là danh sách API app đang gọi | `--list` không quét artifact | Scan JAR/directory riêng |
| Bỏ qua `cannot find class` | Kết quả có thể không đầy đủ | Giải quyết classpath hoặc đánh dấu gap |
| Chạy `jdeps --ignore-missing-deps` rồi báo “all clear” | Bỏ qua thiếu dependency | Quét cuối với dependencies đầy đủ |
| Dùng `-source 21 -target 21` để bảo đảm API Java 21 | Không chặn API mới từ compiler JDK | Dùng `--release 21` |
| Bật `--enable-preview` để né lỗi nâng cấp | Preview không bảo đảm compatibility | Chọn features ổn định hoặc chính sách preview riêng |
| Thêm `-Werror` cho toàn bộ code cũ khi chưa có baseline | Pipeline bỗng fail hàng loạt, khó phân loại | Bật warnings trước, triển khai gates theo giai đoạn |
| `@SuppressWarnings("deprecation")` mọi nơi | Che findings thay vì thay API | Suppress tối thiểu có lý do, kế hoạch sửa |
| Cứ thấy internal thì đổi sang một `jdk.internal.*` khác | Vẫn phụ thuộc implementation | Chọn public API hỗ trợ |
| Mở toàn bộ modules bằng `--add-opens` rồi coi đã nâng xong | Che strong encapsulation issues | Nâng library và opens có scope khi thực sự cần |
| Coi `jdeps` không output là đã chạy tốt | Không kiểm tra dynamic loading và behavior | Integration/smoke tests |
| Nhầm `deprecated` với `removed` | Deprecated không có nghĩa API biến mất | Xem Javadoc, removal notes và actual compiler/runtime errors |
| Quét multi-release JAR với view không đúng | Bỏ sót bytecode chọn ở JDK 27 | `--multi-release 27` |
| So report của JDK khác mà không ghi tool version | Findings thay đổi vì knowledge base | Pin/ghi JDK build và options |
| Đếm số warnings làm KPI duy nhất | Mức nguy hiểm khác nhau | Phân loại rủi ro, owner và SLO/impact |
| Không kiểm thử semantics sau thay thế API | Replacement có thể khác hành vi | Regression tests cho edge cases |
| Quét xong nhưng không chạy runtime image thật | Runtime config/agents có thể khác CI | Smoke test trên deployable image |
| Giữ workaround vô hạn không có owner | Tạo nợ bảo mật và vận hành | Issue, thời hạn, kế hoạch xóa |

## 28. Checklist rà soát trước khi tuyên bố tương thích Java 27

1. **Có dùng đúng JDK 27 cho `java`, `javac`, `jdeps` và `jdeprscan` không?** Đã lưu build/version chưa?
2. **Artifact quét là artifact sẽ deploy?** Có đủ app JAR, dependencies và các module/plugins không?
3. **`jdeps --jdk-internals` có phát hiện unsupported internals?** Đã xác định owner và replacement?
4. **`jdeps --missing-deps` có finding chưa resolve?** Đã kiểm tra đúng classpath/module path?
5. **Với multi-release JAR đã chọn `--multi-release 27` phù hợp chưa?**
6. **Đã dùng `jdeps --api-only` đúng mục đích public API, không thay cho full analysis?**
7. **Đã quét `jdeprscan --release 27` trên compiled artifacts?** Không nhầm với compile warnings?
8. **Đã quét riêng `jdeprscan --for-removal` để ưu tiên remediation?**
9. **Các lỗi `cannot find class` của scanner đã được xử lý?** Báo cáo có ghi scan completeness?
10. **Có nhớ `jdeprscan` không báo third-party deprecated APIs không?**
11. **Compiler đã bật `-Xlint:deprecation,removal,unchecked,rawtypes` ở các source sets phù hợp chưa?**
12. **Với source targeting Java 21/phiên bản thấp hơn, đã dùng `--release` đúng hợp đồng chưa?**
13. **`-Werror` hoặc `-Werror:removal` đã được bật theo giai đoạn phù hợp chưa?**
14. **Các `@SuppressWarnings` có lý do/owner và phạm vi nhỏ không?**
15. **Đã xem release notes của framework, driver, instrumentation agent và native dependencies chưa?**
16. **Có tests cho reflection/ServiceLoader, JNI/native path và module boundary không?**
17. **Đã tìm và xóa hoặc quản lý có thời hạn những `--add-opens`/`--add-exports` workarounds chưa?**
18. **Đã đọc Migration Guide và kiểm tra JVM flags startup thực tế chưa?**
19. **Các thay thế API có regression tests về dữ liệu và semantics không?**
20. **Tests có chạy trên runtime image/container giống production không?**
21. **Có load/performance/security tests cho những workloads quan trọng không?**
22. **Mọi finding đã có artifact, vị trí, mức độ, owner, trạng thái và bằng chứng xử lý chưa?**
23. **Có lưu baseline warnings, command lines, JDK build và artifact hashes?**
24. **Có canary/rollback plan cho đợt nâng cấp không?**
25. **Có quy trình ngăn findings mới xuất hiện sau khi đã đạt baseline sạch không?**

## 29. Tổng kết

Khi nâng cấp lên Java 27, **`jdeps`, `jdeprscan` và `javac -Xlint` giải quyết ba câu hỏi khác nhau**:

- `jdeps` giúp biết bytecode có những **dependency edges** nào, có dùng JDK internals, thiếu classes hoặc đòi module nào. Nó không bảo đảm nhận diện mọi dynamic access.
- `jdeprscan` giúp tìm những usages của **Java SE deprecated APIs**, với `--for-removal` để ưu tiên API có nguy cơ bị xóa. Nó không quét deprecation của mọi third-party library và không thể tự phát hiện mọi removed API.
- `javac` giúp kiểm tra **source**, phát hiện warnings về API lifecycle, kiểu dữ liệu và các vấn đề compilation. Dùng `--release` để bảo vệ hợp đồng target, và `-Werror`/`-Werror:removal` khi đã có baseline sạch.

**Quy trình đúng** không kết thúc khi scanner không in warning: hãy hoàn thiện classpath/module path, xác định ownership, sửa code/đổi dependency, compile lại, re-scan và chạy tests trên đúng runtime image. Mục tiêu là **khả năng tương thích có bằng chứng**, không phải một báo cáo “0 warnings” được tạo ra bằng cách bỏ qua errors hoặc suppress mọi cảnh báo.

## Tài liệu tham khảo

- [Java SE 27 — The jdeps Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — các chế độ phân tích class/module/JAR, `--jdk-internals`, `--missing-deps`, `--api-only`, `--multi-release`.
- [Java SE 27 — The jdeprscan Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html) — quét deprecated Java SE APIs, `--class-path`, `--for-removal`, `--list`.
- [Java SE 27 — The javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`, `-Xlint`, `-Werror`, xử lý compile warnings.
- [Java SE 27 — Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html) — hướng dẫn nâng cấp và các thay đổi có thể ảnh hưởng runtime.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — Java launcher, runtime flags và kiểm tra Java execution environment.
- [Java SE 27 — Deprecated API List](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html) — đối chiếu trạng thái deprecated trong Java SE/JDK API.
- [Java SE 27 — java.lang.Deprecated](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Deprecated.html) — `since` và `forRemoval` semantics.
- [Java SE 27 — java.lang.SuppressWarnings](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/SuppressWarnings.html) — giới hạn và phạm vi của compiler warning suppression.
- [dev.java — jdeprscan](https://dev.java/learn/jvm/tools/core/jdeprscan/) — giải thích phạm vi và cách hiểu deprecated API scanner.
- [OpenJDK — JEP 261: Module System](https://openjdk.org/jeps/261) — nền tảng Java Platform Module System, readability, exports/opens.
