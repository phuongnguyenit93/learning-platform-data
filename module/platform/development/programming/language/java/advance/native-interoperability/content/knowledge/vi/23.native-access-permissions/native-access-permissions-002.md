# `--enable-native-access`: cấp quyền native cho module có tên và `ALL-UNNAMED` trên classpath

## Mục tiêu

Sau bài này, bạn có thể: (1) xác định **module nào thực sự cần quyền native** khi dùng JNI hoặc Foreign Function & Memory (FFM); (2) khởi chạy ứng dụng JPMS với tên module cụ thể, ứng dụng classpath với `ALL-UNNAMED`, hoặc ứng dụng kết hợp cả hai; (3) kiểm chứng quyền được cấp và chẩn đoán cảnh báo/lỗi trên các phiên bản JDK phù hợp; (4) chọn phạm vi quyền nhỏ nhất cần thiết.

## 1. Vì sao JVM cần cờ này?

**Native access** là khả năng của mã Java thực hiện những thao tác có thể đi ra ngoài các bảo đảm an toàn thông thường của JVM, chẳng hạn gọi hàm C bằng FFM, tải thư viện native hoặc tương tác qua JNI. Một lời gọi sai chữ ký hàm, sai địa chỉ, sai vòng đời vùng nhớ, hay thư viện native không đáng tin có thể làm tiến trình JVM sập hoặc gây hỏng bộ nhớ. Vì vậy JDK đánh dấu một số API là *restricted* và tăng cường kiểm soát hoạt động native.

Cú pháp trọng tâm:

```text
java --enable-native-access=<module-name>[,<module-name>...] <cách-khởi-chạy>
java --enable-native-access=ALL-UNNAMED <cách-khởi-chạy>
```

Cờ `--enable-native-access` **cấp quyền cho mã thuộc module được chỉ định** khi mã đó thực hiện thao tác native bị kiểm soát. JVM xét **module của mã gọi thao tác hạn chế** (caller), không phải module chứa lớp `main`, module `java.base` hoặc tên file thư viện `.so`/`.dll`/`.dylib`. Nếu thư viện `com.acme.nativebridge` gọi restricted FFM method thay cho ứng dụng `com.acme.app`, hãy cấp quyền cho `com.acme.nativebridge`.

Cờ này **không** tự tải thư viện, tìm file thư viện, cấp quyền hệ điều hành, kiểm tra chữ ký hàm C, quản lý an toàn con trỏ, hoặc biến native code thành sandbox. Nó cũng không phải `--enable-preview` hay công tắc cho phép reflective access.

## 2. Named module và unnamed module khác nhau thế nào?

| Kiểu triển khai | Module chứa mã | Cách cấp native access | Phạm vi |
| --- | --- | --- | --- |
| JAR/module tường minh trên `--module-path`, có `module-info.java` | Named module, ví dụ `com.acme.nativebridge` | `--enable-native-access=com.acme.nativebridge` | Đúng module được nêu |
| JAR thường đặt trên `--module-path` | Automatic named module, tên có thể đến từ `Automatic-Module-Name` hoặc tên JAR | `--enable-native-access=<tên-module-thực-tế>` | Đúng automatic module đó |
| Lớp/JAR trên `--class-path` hoặc `-cp`, kể cả ứng dụng chạy qua `-jar` | Unnamed module | `--enable-native-access=ALL-UNNAMED` | **Mọi unnamed module**, không chỉ một JAR |
| Ứng dụng phối hợp module path và classpath | Named + unnamed | `--enable-native-access=com.acme.nativebridge,ALL-UNNAMED` | Named module được liệt kê **và** các unnamed module |

**`ALL-UNNAMED` là từ khóa đặc biệt**, không phải tên module do người dùng tự đặt và không có file `module-info.java` tương ứng. Khi nhiều JAR cùng nằm trên classpath, bạn không thể cấp native access chỉ cho một JAR bằng `ALL-UNNAMED`; lựa chọn này mở cho toàn bộ mã thuộc unnamed modules. Nếu cần thu hẹp quyền cho một thư viện, xem xét chuyển JAR đó sang module path dưới dạng named hoặc automatic module và cấp quyền bằng đúng tên của nó.

Mỗi named module có một danh tính riêng, bất kể module nào chứa `main`. Việc `requires com.acme.nativebridge;` trong `module-info.java` chỉ thể hiện quan hệ đọc module, **không truyền native access** từ module A sang B.

## 3. Viết lệnh JVM đúng phạm vi

Các ví dụ dưới đây giả sử có một ứng dụng thực tế đã được biên dịch và đóng gói. Thay đường dẫn/tên module/class bằng cấu trúc dự án của bạn.

**Một named module cần quyền:**

```bash
java --enable-native-access=com.acme.nativebridge --module-path mods -m com.acme.app/com.acme.app.Main
```

Dù `main` ở `com.acme.app`, quyền được cấp cho `com.acme.nativebridge` nếu chính bridge gọi restricted API.

**Hai named modules cùng cần quyền:**

```bash
java --enable-native-access=com.acme.nativebridge,com.acme.plugin --module-path mods -m com.acme.app/com.acme.app.Main
```

Tên phân cách bằng dấu phẩy; tránh chèn dấu cách trong danh sách.

**Ứng dụng classpath:**

```bash
java --enable-native-access=ALL-UNNAMED -cp "app.jar:lib/*" com.acme.app.Main
```

Dấu `:` trong classpath ở trên dành cho Linux/macOS; Windows dùng `;`. Nếu JAR có manifest `Main-Class`, có thể chạy `java --enable-native-access=ALL-UNNAMED -jar app.jar`. Lưu ý `-jar` dùng cơ chế classpath của executable JAR, không tự biến JAR đó thành named module.

**Hỗn hợp module path và classpath:**

```bash
java --enable-native-access=com.acme.nativebridge,ALL-UNNAMED --module-path mods -cp "legacy.jar" -m com.acme.app/com.acme.app.Main
```

Dạng kết hợp chỉ phù hợp khi **cả** bridge named module và một phần mã unnamed thực sự cần native access. Không thêm `ALL-UNNAMED` chỉ để cảnh báo biến mất nếu chưa biết mã gọi đến từ đâu.

**Cần đặt tùy chọn ở đâu?** Đặt tùy chọn của JVM **trước** tên lớp chính, `-m` hoặc `-jar` và bảo đảm chúng được chuyển tới tiến trình `java` thực sự. Đối số đặt **sau** tên main class/đường dẫn ứng dụng thường là đối số truyền vào `main(String[] args)`, không phải JVM option. Nếu chạy qua IDE, Gradle, Maven, application server hoặc container, cấu hình **JVM arguments của tiến trình chạy ứng dụng**, không nhầm với tham số chương trình hoặc compiler.

## 4. Thực hành 1 — kiểm tra module đã được cấp quyền chưa (JDK 22+)

Kể từ JDK 22, `Module.isNativeAccessEnabled()` là API chuẩn để truy vấn quyền của module. Ví dụ dưới đây chỉ đọc trạng thái; **không gọi bất kỳ native function nào**, nên an toàn để kiểm tra named/unnamed module.

Tạo cấu trúc thư mục:

```text
src/
└── com.example.nativeprobe/
    ├── module-info.java
    └── com/example/probe/NativeAccessProbe.java
```

File `src/com.example.nativeprobe/module-info.java`:

```java
module com.example.nativeprobe {
}
```

File `src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java`:

```java
package com.example.probe;

public class NativeAccessProbe {
    public static void main(String[] args) {
        Module current = NativeAccessProbe.class.getModule();
        String name = current.isNamed() ? current.getName() : "<unnamed>";
        System.out.println("module=" + name);
        System.out.println("nativeAccessEnabled=" + current.isNativeAccessEnabled());
    }
}
```

### 4.1 Chạy dưới dạng classpath/unnamed module

Các lệnh shell sau dành cho Bash trên Linux/macOS hoặc môi trường tương thích; Windows có thể tạo thư mục bằng lệnh tương đương. Chạy tại thư mục chứa `src`:

```bash
mkdir -p build/classes build/mods/com.example.nativeprobe
javac -d build/classes src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java

java -cp build/classes com.example.probe.NativeAccessProbe
java --enable-native-access=ALL-UNNAMED -cp build/classes com.example.probe.NativeAccessProbe
```

**Stdout lệnh 1:**

```text
module=<unnamed>
nativeAccessEnabled=false
```

**Stdout lệnh 2:**

```text
module=<unnamed>
nativeAccessEnabled=true
```

Việc không biên dịch `module-info.java` vào `build/classes` khiến lớp chạy trên classpath thuộc unnamed module. `ALL-UNNAMED` khiến trạng thái chuyển từ `false` sang `true`.

### 4.2 Chạy dưới dạng named module

```bash
javac -d build/mods/com.example.nativeprobe src/com.example.nativeprobe/module-info.java src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java

java --module-path build/mods -m com.example.nativeprobe/com.example.probe.NativeAccessProbe
java --enable-native-access=com.example.nativeprobe --module-path build/mods -m com.example.nativeprobe/com.example.probe.NativeAccessProbe
```

**Stdout lệnh 1:**

```text
module=com.example.nativeprobe
nativeAccessEnabled=false
```

**Stdout lệnh 2:**

```text
module=com.example.nativeprobe
nativeAccessEnabled=true
```

Lúc này class được đóng gói trong named module; tên cấp quyền là `com.example.nativeprobe`. Dùng riêng `ALL-UNNAMED` sẽ **không** cấp native access cho module này. Khi thử với JDK 17–21, đừng sao chép nguyên ví dụ truy vấn `isNativeAccessEnabled()`: API này trở thành chuẩn ở JDK 22; các bản trước có vòng đời preview/incubator khác nhau.

## 5. Thực hành 2 — thấy tác động lên một restricted FFM method (JDK 24+)

Trong JDK 24+, `--illegal-native-access` cho phép kiểm tra chính sách trước khi JDK chuyển sang mặc định nghiêm ngặt hơn. Ví dụ dưới đây cố ý **chỉ tạo downcall method handle**, không gọi địa chỉ native nào:

File `RestrictedProbe.java` tại thư mục đang làm việc:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;

public class RestrictedProbe {
    public static void main(String[] args) {
        Linker.nativeLinker().downcallHandle(FunctionDescriptor.ofVoid());
        System.out.println("Restricted downcall handle created");
    }
}
```

```bash
javac RestrictedProbe.java

java --illegal-native-access=deny RestrictedProbe
java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED RestrictedProbe
```

- **Lệnh đầu:** module unnamed chưa được cấp quyền; khi gọi `downcallHandle` bị chặn với `IllegalCallerException`, nên không in dòng thành công.
- **Lệnh sau:** `ALL-UNNAMED` cấp quyền cho caller; stdout chính xác là:

```text
Restricted downcall handle created
```

Nếu chạy `java RestrictedProbe` trên JDK 24+ với chính sách mặc định `warn`, thao tác thường vẫn được phép và JVM ghi cảnh báo ra **stderr**; nội dung cụ thể của cảnh báo có thể khác giữa các phiên bản JDK. **Tạo handle không chứng minh rằng một địa chỉ native hay chữ ký C tùy ý là an toàn để gọi**; bài thực hành chủ động không invoke handle.

### Cảnh báo và lỗi theo phiên bản JDK

| Nhóm phiên bản | Điểm cần nhớ |
| --- | --- |
| JDK 17–21 | FFM còn thay đổi theo incubator/preview; kiểm tra đúng tài liệu JDK và các cờ build/run tương ứng. `--enable-native-access` đã xuất hiện để kiểm soát restricted FFM API, nhưng không mặc định suy ra mọi quy tắc JNI mới hơn. |
| JDK 22–23 | FFM API được chuẩn hóa từ JDK 22. Restricted FFM calls và `--enable-native-access` được áp dụng; cách xử lý truy cập không được cấp quyền cần đối chiếu tài liệu đúng phiên bản (trên JDK 22, việc chỉ định `--enable-native-access` có thể khiến caller nằm ngoài danh sách bị `IllegalCallerException`). |
| JDK 24+ | JEP 472 mở rộng cơ chế giới hạn/cảnh báo để chuẩn bị siết JNI. `--illegal-native-access=allow` cho phép không cảnh báo, `warn` cho phép nhưng cảnh báo (mặc định ở các bản JDK 24–26), `deny` chặn bằng `IllegalCallerException`. Mặc định `deny` được dự kiến áp dụng ở một bản tương lai, không được giả định đã có ở mọi JDK. |

Trên JDK 24+, kiểm thử tích hợp với `--illegal-native-access=deny` là cách tìm quyền còn thiếu **trước** khi chuyển runtime. Không dùng `allow` như biện pháp sửa lâu dài chỉ nhằm che cảnh báo.

## 6. Cách lựa chọn quyền trong dự án có nhiều thư viện

Giả sử ứng dụng `com.acme.app` gọi `com.vendor.image`; bên trong `com.vendor.image` có lời gọi JNI/FFM bị hạn chế. Xác định **thư viện chứa caller**:

1. Kiểm tra stack trace/cảnh báo JVM để biết module của mã gọi restricted method, hoặc xem lớp khai báo `native` / nơi gọi `System.loadLibrary`, `Linker.downcallHandle`, v.v.
2. Kiểm tra cách JAR được đưa vào JVM: `--class-path` → unnamed; `--module-path` → named (có thể là automatic module).
3. Nếu là named module, kiểm tra tên module thực tế bằng `jar --describe-module --file path/to/library.jar` hoặc thông tin module của ứng dụng. Không suy đoán tên module bằng package name.
4. Cấp quyền cho module **đúng caller**. Chạy lại với `--illegal-native-access=deny` trên JDK 24+ và xem còn caller nào thiếu quyền.
5. Nếu thư viện phải ở classpath, dùng `ALL-UNNAMED` với hiểu biết rằng phạm vi này rộng. Khi phù hợp, đưa JAR cần quyền lên module path để hạn chế quyền theo module; cần kiểm tra tương thích module/dependency trước khi chuyển.

Quyền này gắn với **module**, không tự lan theo `requires`, dependency transitively, module chứa `main` hay đối tượng Java truyền qua API. Một named module không được hưởng quyền chỉ vì unnamed module khác được cấp `ALL-UNNAMED`.

### Những cách cấu hình khác

- **Biến môi trường `JDK_JAVA_OPTIONS`**: launcher đọc JVM options từ biến này, hữu ích khi không kiểm soát trực tiếp lệnh khởi động. Cần cấu hình ở đúng container/process, kiểm tra tác động chung đến các lệnh `java` được khởi chạy từ môi trường đó.
- **Argument file**: ghi tùy chọn vào file (ví dụ `runtime.options`) và chạy `java @runtime.options ...`; quy tắc chọn module vẫn y hệt.
- **Manifest của executable JAR**: thuộc tính `Enable-Native-Access: ALL-UNNAMED` có thể cấp quyền cho classpath khi chạy `java -jar`. Thuộc tính này **không nhận tên named module** và không thay thế thiết lập cho `--module-path`.
- **Module layer động**: `ModuleLayer.Controller.enableNativeAccess(module)` hỗ trợ tình huống đặc thù, nhưng bản thân thao tác này là restricted và phải tuân thủ điều kiện caller có native access. Đừng xem đây là lối vượt quyền tùy ý.

## 7. Phân biệt với các cờ JVM dễ nhầm

| Cờ | Mục đích |
| --- | --- |
| `--enable-native-access=M` | Cho phép mã trong module `M` thực hiện restricted/native access theo chính sách JDK |
| `--enable-native-access=ALL-UNNAMED` | Cho phép các unnamed modules thực hiện native access; ảnh hưởng toàn classpath |
| `--add-opens=module/package=target` | Mở package cho deep reflection, **không** tự cấp native access |
| `--add-exports=module/package=target` | Xuất package để module khác dùng kiểu public, **không** tự cấp native access |
| `--enable-preview` | Cho phép dùng preview language/API của JDK tương ứng; **không** thay cho quyền native |
| `-Djava.library.path=...` | Hỗ trợ JVM tìm thư viện native theo tên ở một số cơ chế tải thư viện; **không** cấp native access và không bảo đảm file đúng kiến trúc/ABI |

### Các lỗi thường gặp và hướng xử lý

- **Đặt `--enable-native-access` sau main class**: main nhận chuỗi đó như đối số ứng dụng; hãy chuyển cờ đến JVM arguments trước main class/`-m`/`-jar`.
- **Chỉ cấp `ALL-UNNAMED` nhưng caller là named module**: thêm đúng module name; `ALL-UNNAMED` không bao phủ named modules.
- **Chỉ cấp tên module của ứng dụng nhưng restricted API nằm trong module thư viện**: sửa danh sách theo module của caller thực tế.
- **Đoán tên automatic module từ package/JAR mà không kiểm tra**: dùng `jar --describe-module`, manifest `Automatic-Module-Name` hoặc metadata JPMS.
- **Bị `IllegalCallerException` ở JDK 24+ với `deny`**: tìm nơi gọi restricted method và cấp quyền tối thiểu cần thiết; đừng vội bật `allow` cho toàn bộ.
- **Bị `UnsatisfiedLinkError` hoặc lỗi tải `.dll/.so/.dylib` sau khi đã cấp quyền**: kiểm tra tên/đường dẫn thư viện, biến môi trường, native dependency, hệ điều hành/CPU/ABI; cờ native access không sửa lỗi liên kết.
- **Tưởng warning biến mất nghĩa là native code an toàn**: các rủi ro use-after-free, sai function descriptor, sai concurrency hoặc thư viện không đáng tin vẫn tồn tại.
- **Dùng hành vi JDK mới để suy luận JDK cũ**: cùng một cờ nhưng các restricted API và cách xử lý cảnh báo đã thay đổi; xác nhận `java -version` và release notes của runtime thật.

## 8. Bảng quyết định nhanh

| Triển khai thực tế | Lệnh/giá trị nên chọn |
| --- | --- |
| Chỉ `com.acme.bridge` (named) gọi native | `--enable-native-access=com.acme.bridge` |
| `com.acme.bridge` và `com.acme.plugin` đều gọi native | `--enable-native-access=com.acme.bridge,com.acme.plugin` |
| Native caller nằm trong một JAR trên classpath | `--enable-native-access=ALL-UNNAMED` (cân nhắc chuyển sang named module nếu muốn thu hẹp) |
| Cả named module `com.acme.bridge` lẫn code classpath gọi native | `--enable-native-access=com.acme.bridge,ALL-UNNAMED` |
| Ứng dụng thuần Java, không thực hiện restricted/native operation | Không cần thêm cờ chỉ vì ứng dụng có dependency thông thường |

**Tự kiểm tra:** Nếu `com.example.app` chạy từ module path, `vendor.legacy.jar` chạy trên classpath, và **chỉ** thư viện legacy gọi restricted FFM API, `--enable-native-access=com.example.app` có đủ không? **Không.** Caller thuộc unnamed module nên cần `ALL-UNNAMED`, hoặc chuyển thư viện sang module path rồi cấp quyền theo tên module của nó. Đổi ngược lại: nếu chỉ `com.example.app` gọi restricted method, riêng `ALL-UNNAMED` cũng không đủ.

## 9. Tài liệu chuẩn để đối chiếu

- Oracle, [`java` launcher, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `--enable-native-access` và `--illegal-native-access`.
- Oracle, [Restricted Methods, JDK 25](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html): cách cấp quyền cho named/unnamed modules, lựa chọn quyền hẹp.
- Oracle, [JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): ảnh hưởng của JEP 472 lên JNI/FFM và cách kiểm tra `deny`.
- Oracle, [`java.lang.Module`, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `isNativeAccessEnabled()`.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454) và [JEP 472](https://openjdk.org/jeps/472): bối cảnh FFM API và hạn chế native access.
