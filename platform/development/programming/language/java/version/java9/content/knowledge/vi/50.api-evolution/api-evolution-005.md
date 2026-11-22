# Java 9+: Giới hạn quét tĩnh và kiểm tra phụ thuộc lúc chạy khi API tiến hóa

## 1. Vì sao cần cả quét tĩnh lẫn kiểm thử lúc chạy?

Khi nâng phiên bản JDK, thay thư viện hoặc tạo runtime image tối giản, ứng dụng Java có thể **biên dịch được** và các công cụ phân tích báo **không có phụ thuộc bất thường**, nhưng vẫn lỗi khi khởi động một tính năng cụ thể. Lý do quan trọng: **phụ thuộc thể hiện trực tiếp trong bytecode** không bao phủ mọi **phụ thuộc chỉ được quyết định khi chạy**.

Hai câu hỏi phải được kiểm tra độc lập:

1. **Quét tĩnh:** những class, package, module và Java SE API nào được mã đã biên dịch tham chiếu trực tiếp? Có API được đánh dấu deprecated hoặc deprecated for removal? Có tham chiếu đến JDK internals?
2. **Kiểm tra runtime:** trên đúng JVM, classpath, module path, plugin, driver, cấu hình và runtime image sản phẩm, những type/provider và thao tác mà chức năng thực sự cần có tìm thấy, nạp, liên kết và chạy thành công hay không?

Trong bối cảnh **Tiến hóa API** của Java 9+, ta thường dùng **`jdeprscan`**, **`jdeps`**, kiểm tra build bằng `javac` và **chạy test trên runtime mục tiêu**. Các công cụ này vẫn có mặt trong JDK hiện hành và bổ trợ nhau.

> **Quét tĩnh sạch không đồng nghĩa ứng dụng chạy được trong mọi môi trường.** Ngược lại, một lần chạy thử thành công cũng không chứng minh tất cả nhánh tùy chọn đều hoạt động. Cần kết hợp quét artifact thực tế với kiểm thử đúng những môi trường và đường đi mà sản phẩm hỗ trợ.

## 2. Ba lớp kiểm tra và trách nhiệm của từng lớp

| Lớp | Công cụ hoặc kỹ thuật | Phát hiện tốt | Không bảo đảm |
|---|---|---|---|
| **API deprecation** | `jdeprscan`, cảnh báo `javac -Xlint:deprecation` | Lời gọi trực tiếp đến Java SE API deprecated mà tool biết; ưu tiên API có `forRemoval=true`. | Không bao quát mọi thư viện bên thứ ba, class tải động hoặc toàn bộ hành vi ứng dụng. |
| **Phụ thuộc bytecode/module** | `jdeps`, `module-info.java`, build dependency graph | Tham chiếu class/package/module tĩnh, một số dependency bị thiếu, tham chiếu đến JDK internals. | Không tìm chắc chắn mọi class được gọi qua chuỗi, reflection, ServiceLoader, plugin hay native library. |
| **Khả năng chạy thực tế** | Smoke/integration/contract tests trên JDK và runtime image cuối | Lỗi load/link, provider thiếu, quyền truy cập module, khác biệt thư viện và hành vi trên nhánh được chạy. | Không chứng minh các nhánh chưa thử đã đúng. |

**`jdeprscan` không phải `jdeps`:** `jdeprscan` quét **cách dùng API Java SE deprecated**; `jdeps` lập **đồ thị phụ thuộc class/module tĩnh**. Một dự án thường cần cả hai khi nâng JDK.

## 3. Quét API deprecated bằng `jdeprscan`

`jdeprscan` được giới thiệu trong JDK 9 và vẫn là công cụ phân tích tĩnh hiện hành. Nó đọc class file, thư mục chứa class hoặc JAR. Ví dụ, sau khi build:

~~~bash
jdeprscan build/classes
jdeprscan app.jar
jdeprscan --for-removal app.jar
~~~

- `jdeprscan app.jar` tìm lời gọi trực tiếp từ bytecode đến **Java SE API deprecated** được tool nhận diện.
- `--for-removal` lọc nhóm API có nguy cơ bị xóa ở một phiên bản tương lai. **Deprecated** không đồng nghĩa API đã bị xóa ngay; mức độ ưu tiên sửa còn tùy trạng thái API và kế hoạch nâng JDK.
- Dùng `--class-path` để cung cấp các thư viện cần cho quá trình phân tích. Nếu tool báo `cannot find class ...`, phải xử lý dependency thiếu trong lần quét; không được suy ra rằng các class đã quét hoàn toàn an toàn.
- `--release` chọn bộ dữ liệu deprecation theo Java SE release **được chính phiên bản tool hỗ trợ**. Không nhầm với `javac --release` (biên dịch cho Java target). Kiểm tra `jdeprscan --help` trên JDK đang dùng vì phạm vi version được chấp nhận thay đổi.

**Giới hạn quan trọng của `jdeprscan`:**

1. Nó chỉ báo **deprecation của Java SE API**, không tổng hợp mọi `@Deprecated` trong các thư viện Maven/Gradle.
2. Nó phân tích **các artifact được cung cấp**; một JAR/plugin không đưa vào scan có thể bị bỏ sót.
3. Tên class/member lấy từ config, reflection, script hoặc runtime code generation **không phải lúc nào trở thành tham chiếu bytecode trực tiếp**.
4. Không dùng tool để chứng minh không có lỗi binary compatibility, không có behavior change hoặc không có phụ thuộc runtime khác.

Để phát hiện cảnh báo ngay trong source hiện có, compiler vẫn hữu ích:

~~~bash
javac -Xlint:deprecation MyApp.java
javac --release 17 MyApp.java
~~~

`-Xlint:deprecation` yêu cầu thông báo chi tiết về việc dùng API deprecated trong mã nguồn mà compiler xử lý. `--release 17` kiểm tra khả năng biên dịch với API và class file target của Java 17. Hai lệnh có **nhiệm vụ khác nhau**; biên dịch thành công vẫn cần runtime test.

## 4. Phân tích phụ thuộc bằng `jdeps`

`jdeps` là công cụ JDK đọc class/JAR và xác định **phụ thuộc tĩnh**. Những lệnh phù hợp khi rà soát bản build:

~~~bash
# Danh sách module rút gọn theo tham chiếu tĩnh:
jdeps --print-module-deps app.jar

# Xem quan hệ giữa các class:
jdeps -verbose:class app.jar

# Tìm dependency chưa phân giải được từ artifact được quét:
jdeps --missing-deps app.jar

# Tìm tham chiếu tĩnh tới API nội bộ của JDK:
jdeps --jdk-internals app.jar
~~~

Với ứng dụng có JAR ngoài, phải cấp đúng `--class-path`/`--module-path`. Với **multi-release JAR**, chọn `--multi-release 17` (hoặc phiên bản mục tiêu) để phân tích đúng biến thể class. `--ignore-missing-deps` chỉ bảo tool bỏ qua phụ thuộc thiếu trong tình huống nhất định; **nó không sửa dependency và không phát hiện class động**.

`--print-module-deps` hữu ích để đưa ra một tập module **ban đầu** khi đóng gói runtime qua `jlink`. Nhưng danh sách có thể chưa bao gồm module chỉ được nạp khi chạy bằng reflection, ServiceLoader, plugin hoặc cấu hình. **Không sử dụng danh sách đó như bằng chứng duy nhất rằng custom runtime image đã đủ module.**

### 4.1. Ví dụ đối chiếu trực tiếp và gián tiếp

~~~java
// Có tham chiếu kiểu trực tiếp tới API java.sql:
java.sql.DriverManager.getDrivers();
~~~

Nếu bytecode chứa lời gọi kiểu trên, `jdeps` có thể suy ra module `java.sql`.

~~~java
// Tên class chỉ là String, được tìm khi chạy:
Class.forName("java.sql.DriverManager");
~~~

Ở ví dụ thứ hai, chuỗi `"java.sql.DriverManager"` **không tạo ra class reference tĩnh** đến `java.sql.DriverManager` trong bytecode theo cách `jdeps` phân tích. Nó có thể chỉ báo `java.base`, mặc dù đường chạy sẽ cần class thuộc `java.sql`. Đây là giới hạn của mô hình phân tích bytecode, không phải lỗi Java.

## 5. Demo Java 17+ thực chạy: `jdeps` bỏ sót module được nạp động

Đây là chương trình **độc lập, biên dịch được**, dùng API còn được hỗ trợ hiện nay. Nó không dùng API đã bị loại bỏ hay deprecated để tạo lỗi.

Tạo tệp **`RuntimeDependencyProbe.java`**:

~~~java
public final class RuntimeDependencyProbe {
    public static void main(String[] args) {
        String name = "java.sql.DriverManager";

        try {
            System.out.println("Runtime: "
                    + Class.forName(name).getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("Runtime: missing " + name);
        }
    }
}
~~~

### Bước A — Biên dịch và xem các module mà `jdeps` phát hiện

Chạy trong thư mục chứa file nguồn trên:

~~~bash
javac --release 17 RuntimeDependencyProbe.java
jdeps --print-module-deps RuntimeDependencyProbe.class
~~~

Đầu ra từ riêng `jdeps` đã được xác minh trên **OpenJDK 24**:

~~~text
java.base
~~~

Nguyên nhân: bytecode trực tiếp dùng `String`, `Class`, `System` và `ClassNotFoundException` thuộc module `java.base`. Tên `"java.sql.DriverManager"` chỉ là giá trị string sẽ được giải nghĩa tại runtime.

### Bước B — Chạy với JDK đầy đủ

~~~bash
java -cp . RuntimeDependencyProbe
~~~

Trên JDK 24 đầy đủ, stdout là:

~~~text
Runtime: java.sql.DriverManager
~~~

Điều này xác nhận đường thử vừa chạy **tìm thấy class**; nó chưa kết nối tới database hay xác nhận JDBC driver cụ thể.

### Bước C — Giới hạn module quan sát được khi chạy

~~~bash
java --limit-modules java.base -cp . RuntimeDependencyProbe
~~~

Khi chỉ cho phép module `java.base`, stdout đã kiểm chứng:

~~~text
Runtime: missing java.sql.DriverManager
~~~

`--limit-modules java.base` là **tham số Java launcher để kiểm thử khả năng nhìn thấy module**, không phải thao tác xóa module khỏi JDK đang cài đặt. Class `java.sql.DriverManager` không thể được nạp trong cấu hình bị giới hạn nên `Class.forName` ném `ClassNotFoundException`, chương trình bắt ngoại lệ để in thông báo.

### Ý nghĩa của thí nghiệm

| Lượt kiểm tra | Kết quả | Kết luận chính xác |
|---|---|---|
| Quét bytecode bằng `jdeps` | `java.base` | Công cụ thấy phụ thuộc **tĩnh** vào `java.base`. |
| Chạy trên JDK đầy đủ | `Runtime: java.sql.DriverManager` | Nhánh thực thi này nạp được `java.sql.DriverManager` ở môi trường đó. |
| Chạy với `--limit-modules java.base` | `Runtime: missing java.sql.DriverManager` | Nhánh thực thi có **phụ thuộc động** mà kết quả `jdeps` không thể hiện. |

Một custom image được tạo bằng `jlink` mà thiếu module `java.sql` có thể gặp hiện tượng tương tự. Vì vậy khi đóng gói image, cần tổng hợp các module do **reflection/config/provider** yêu cầu và chạy smoke test trên **chính image cuối**, thay vì chỉ tin vào graph quét tĩnh.

## 6. Những phụ thuộc tĩnh thường không thấy đầy đủ

### Reflection và tên được tính khi chạy

Các dạng như `Class.forName(classNameFromConfig)`, `ClassLoader.loadClass(...)`, reflection gọi member theo tên hoặc plugin chọn theo properties có thể nạp những class không xuất hiện dưới dạng tham chiếu tĩnh. Một string literal đôi khi có thể được công cụ phân tích chuyên dụng dò thấy, nhưng **`jdeps` không cam kết suy luận tất cả tên class từ string/config hoặc logic chương trình**.

### `ServiceLoader` và provider module

Mã có thể chỉ tham chiếu **service interface**, còn provider implementation được tìm khi chạy qua `ServiceLoader`, `META-INF/services` hoặc `provides ... with ...` trong module descriptor. Nếu module/JAR của provider không được đóng gói, ứng dụng có thể không tìm thấy dịch vụ hoặc gặp `ServiceConfigurationError`.

`jlink --bind-services` có thể hỗ trợ thêm provider module cùng phụ thuộc vào runtime image khi phù hợp, nhưng vẫn cần chạy kiểm thử tìm/chọn **đúng provider** mà ứng dụng sử dụng. Không phải mọi plugin được lấy từ thư mục ngoài đều tự được giải quyết bởi `jlink`.

### Driver, native library và cấu hình

Một JDBC driver chỉ có trong runtime classpath, native library dùng bởi JNI/FFM, resource bundle, file cấu hình hoặc plugin tùy từng môi trường có thể không nằm trong đồ thị class dependency tĩnh. Quét thành công không chứng minh rằng driver cấu hình đúng hay thư viện native tương thích với hệ điều hành/kiến trúc đang deploy.

### Runtime image và module encapsulation

Có module chưa chắc đã có **quyền truy cập** mọi thành phần. JPMS phân biệt module có mặt, đọc được, package được `exports` và mức mở `opens` cho deep reflection. Trên JDK 17+ strong encapsulation của các API JDK nội bộ được thực thi chặt hơn mặc định; các framework cũ truy cập member nội bộ có thể gặp `InaccessibleObjectException` dù class vẫn tồn tại.

`jdeps --jdk-internals` có thể phát hiện **tham chiếu tĩnh** tới JDK internals, nhưng không chứng minh mọi đường reflection đều hợp lệ. Ưu tiên API public được hỗ trợ, khai báo `opens` có phạm vi rõ khi thực sự cần; tránh mở hàng loạt package chỉ để che lỗi nâng JDK.

## 7. Phân loại các lỗi runtime cần thử

| Triệu chứng | Ý nghĩa điển hình | Cách xác minh |
|---|---|---|
| `ClassNotFoundException` | Code tìm class theo tên nhưng runtime/classloader không thấy. | Kiểm tra tên type, JAR, module path và môi trường chạy nhánh đó. |
| `NoClassDefFoundError` | JVM cần class đã tham chiếu nhưng không nạp/khởi tạo được theo trạng thái hiện tại. | Kiểm tra cause, dependency bắc cầu, class initialization, runtime classpath. |
| `NoSuchMethodError` / `NoSuchFieldError` | Bytecode được biên dịch với member khác với class ở runtime; thường là lệch phiên bản dependency. | So sánh version dependency khi compile và khi deploy; thử gọi method thật. |
| `InaccessibleObjectException` | Reflection bị từ chối do quyền truy cập member/package/module. | Kiểm tra `module-info.java`, package opens và API thay thế. |
| `ServiceConfigurationError` | Provider thiếu, service descriptor lỗi hoặc provider không khởi tạo được. | Thử `ServiceLoader` với đúng classloader/module layer, kiểm tra metadata và JAR. |
| `UnsatisfiedLinkError` | Không tìm được native library hoặc ABI/kiến trúc không khớp. | Kiểm tra image OS/architecture, đường tìm thư viện và cách package. |
| Không báo lỗi nhưng plugin bị mất | Không có provider được tìm hoặc feature flag không bật. | Assert số lượng/provider identity, chạy test theo profile. |
| Chạy được nhưng xử lý dữ liệu khác trước | Thay đổi behavior/default của API hoặc môi trường không gây linkage error. | Regression/contract tests với dữ liệu thực tế và phiên bản JDK mục tiêu. |

Không nên coi tất cả lỗi này chỉ xuất hiện từ Java 9: chúng là những rủi ro vẫn hiện hữu trên JDK hiện hành khi API và cách đóng gói ứng dụng thay đổi.

## 8. Quy trình kiểm tra thực tế trước khi phát hành

### 8.1. Chốt đúng artifact và cấu hình

Ghi rõ bản JDK, hệ điều hành, kiến trúc CPU, JAR/module sẽ deploy, bản dependency trực tiếp và bắc cầu, launcher flags, classpath/module path, runtime image, plugin và driver. Nếu CI build khác production, dùng **artifact sản phẩm cuối** để kiểm tra lại.

### 8.2. Quét static theo đúng phạm vi

Chạy `jdeprscan` để tìm Java SE API deprecated và `jdeps` để thấy phụ thuộc tĩnh. Quét cả những JAR quan trọng, không chỉ app JAR. Nếu tool báo thiếu class cần cho phân tích, sửa classpath/module path và chạy lại; đừng lạm dụng `--ignore-missing-deps`.

~~~bash
jdeprscan app.jar
jdeprscan --for-removal app.jar

jdeps --print-module-deps app.jar
jdeps --missing-deps app.jar
jdeps --jdk-internals app.jar
~~~

Nếu có multi-release JAR, dùng `jdeps --multi-release` theo runtime mục tiêu. Để xem API của phiên bản Java cụ thể, dùng tài liệu Java SE hiện tại và các ghi chú migration; `jdeprscan` không phải một hệ thống kiểm tra toàn bộ hành vi phần mềm.

### 8.3. Liệt kê các phụ thuộc chỉ xuất hiện lúc chạy

Đọc cấu hình plugin, SPI providers, reflection/classloader, JDBC drivers, native libraries, resource files, feature flags và profile. Với mỗi phụ thuộc quan trọng, quyết định test runtime nào phải chạy và điều gì là kết quả mong đợi.

Có thể dùng phép kiểm tra class hiện diện mà **không chủ động khởi tạo nó**:

~~~java
// Đoạn minh họa trong phương thức Java; cần bắt/throws ClassNotFoundException.
Class<?> type = Class.forName(
        "java.sql.DriverManager",
        false,
        Thread.currentThread().getContextClassLoader());
System.out.println(type.getName());
~~~

Tham số `false` tránh **khởi tạo class trong lời gọi này**, nhưng vẫn có thể có thao tác nạp/liên kết; đây chỉ là phép thử **tìm type**, không đảm bảo constructor/method/driver/service chạy được. Test chức năng thực tế mới xác nhận chuỗi phụ thuộc đầy đủ.

### 8.4. Kiểm thử trên môi trường đúng như production

- Chạy **smoke test khởi động** bằng JDK/runtime image cuối cùng.
- Chạy **integration tests** qua chức năng thực tế: kết nối database, tìm SPI provider, reflection, plugin loading, native library.
- Chạy các profile và feature flag tùy chọn, kể cả nhánh có dependency riêng và nhánh fallback khi dependency không tồn tại.
- Kiểm tra module access, logging, lỗi security policy, classpath/module-path và quyền file.
- Khi đổi version library, chạy test API contract để phát hiện thay đổi behavior hoặc binary signature; không chỉ kiểm tra class có tồn tại.

Ghi kết quả theo **artifact + runtime + profile + test case**. Một nhánh chưa test phải được ghi rõ là chưa xác minh, thay vì gọi toàn bộ sản phẩm “đã kiểm tra runtime”.

## 9. Bốn tình huống thường gặp khi API tiến hóa

**Tình huống A — Runtime image thiếu module.** Một plugin chỉ gọi `Class.forName("java.sql.DriverManager")` khi bật profile database. `jdeps` báo `java.base` nên image tạo ra thiếu `java.sql`. Test trên image này phát hiện ngay lỗi. Cách sửa: đưa module và JDBC driver phù hợp vào deployment, chạy lại nhánh kết nối thực.

**Tình huống B — Dependency dùng Java SE API deprecated.** Ứng dụng chính được compile mới, nhưng một thư viện JAR có sẵn vẫn dùng API deprecated for removal. `jdeprscan` trên JAR đó giúp xác định nguy cơ; cập nhật/thay thư viện trước khi nâng JDK và chạy test chức năng liên quan.

**Tình huống C — Service provider bị thiếu.** Code compile với một SPI interface nhưng provider module không được đưa vào runtime image hoặc classpath. `jdeps` không thể kết luận một provider động sẽ tồn tại. Test `ServiceLoader` và thao tác qua provider, kiểm tra module/JAR đăng ký dịch vụ rồi đóng gói lại.

**Tình huống D — Reflection bị hạn chế.** Một framework tìm được type nhưng truy cập private member của JDK class bị từ chối trên JDK mới do strong encapsulation. Giải pháp bền vững là thay bằng API được hỗ trợ, chỉnh thiết kế module hoặc nâng thư viện framework; dùng tùy chọn mở package chỉ khi cần và đã đánh giá phạm vi.

## 10. Những ngộ nhận cần tránh

1. **“Không có kết quả `jdeprscan` là không còn dependency nguy hiểm.”** Sai: nó tập trung vào Java SE API deprecated, không quét tất cả dependency và hành vi.
2. **“`jdeps --print-module-deps` trả `java.base` nghĩa app chắc chắn chỉ cần `java.base`.”** Sai khi có reflection/ServiceLoader/config. Thí nghiệm `java.sql` chứng minh.
3. **“`--ignore-missing-deps` đã sửa class thiếu.”** Sai: đó là tùy chọn phân tích, không thay đổi runtime.
4. **“Dùng `javac --release 17` thì JDK 17+ bất kỳ đều chạy được.”** Sai: còn module, dependency, native library, chính sách và tương thích binary.
5. **“Tìm được class bằng reflection nghĩa mọi method đều gọi được.”** Sai: còn member signature, initialization, module access và dependency bắc cầu.
6. **“`jdeprscan` tìm mọi API deprecated của third-party.”** Sai: nó kiểm tra tập Java SE API được hỗ trợ bởi tool.
7. **“Tạo image bằng `jlink` với module `jdeps` liệt kê là đủ.”** Chỉ đúng nếu đã xử lý đầy đủ các phụ thuộc động/provider cần thiết và xác minh runtime.
8. **“Một lần main chạy được chứng minh mọi plugin hoạt động.”** Sai: chỉ những nhánh đã được kích hoạt mới được kiểm tra.
9. **“Mọi lỗi do thiếu class.”** Sai: còn mismatch method/field, lỗi service, reflection access và behavior thay đổi.
10. **“Quét tĩnh thay thế kiểm thử runtime.”** Sai: hai phương pháp xử lý những nguy cơ khác nhau và cần dùng cùng nhau.

## 11. Câu hỏi tự kiểm tra

**1.** `jdeps --print-module-deps` chỉ báo `java.base` nhưng code có `Class.forName("java.sql.DriverManager")`. Có chắc xóa `java.sql` khỏi runtime image an toàn không?

**Đáp án:** Không. Đây là phụ thuộc động mà `jdeps` không suy ra qua string. Phải kiểm thử nhánh đó trên runtime image cuối.

**2.** `jdeprscan app.jar` không có cảnh báo. Có đảm bảo các thư viện Maven không dùng API deprecated không?

**Đáp án:** Không. Công cụ báo deprecated **Java SE API**, không tổng hợp deprecation của mọi thư viện ngoài.

**3.** Lệnh nào tìm phụ thuộc tĩnh vào API JDK nội bộ?

**Đáp án:** `jdeps --jdk-internals app.jar`, kết hợp kiểm tra reflection và runtime tests.

**4.** `ClassNotFoundException` khác `NoSuchMethodError` ở đâu?

**Đáp án:** Một trường hợp không tìm thấy type khi tải class theo tên; trường hợp kia JVM tìm được type nhưng không có member mà bytecode yêu cầu, thường vì khác bản thư viện.

**5.** `javac --release 17` có kiểm tra tài nguyên runtime được đóng gói trong image không?

**Đáp án:** Không. `--release` tập trung kiểm tra nguồn và API mục tiêu; image, driver và plugin phải được kiểm tra riêng khi chạy.

**6.** Có nên chỉ chạy smoke test với cấu hình mặc định?

**Đáp án:** Không, nếu sản phẩm có các profile/feature flag kích hoạt provider hoặc module riêng. Chạy các nhánh thực sự được hỗ trợ và ghi rõ nhánh chưa kiểm tra.

## Tài liệu tham khảo hiện hành

- [Java SE 26 — `jdeprscan`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html): phạm vi scan bytecode/JAR, `--for-removal`, `--class-path` và các giới hạn Java SE deprecation.
- [Java SE 26 — `jdeps`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): phụ thuộc tĩnh, `--print-module-deps`, `--missing-deps`, `--jdk-internals`, multi-release JAR.
- [Java SE 26 — công cụ `java`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `--limit-modules` và các tùy chọn JPMS runtime.
- [Java SE 26 — công cụ `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--release` và cảnh báo compiler.
- [Java SE 26 — `Class.forName`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): nạp class theo tên.
- [Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): dịch vụ và provider được phát hiện động.
- [Java SE 26 — `jlink`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): tạo runtime image và tùy chọn `--bind-services`.
- [Java SE 26 — Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): module system, class loader và strong encapsulation.
- [Java SE 26 — Deprecated API](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html): tình trạng API Java SE bị deprecated.

**Ghi nhớ:** `jdeprscan` trả lời **API Java SE nào đã deprecated?**; `jdeps` trả lời **bytecode tham chiếu tĩnh tới đâu?**; còn **kiểm thử trên runtime thực tế** mới đánh giá được lớp phụ thuộc động và hành vi khi các nhánh ứng dụng thực sự chạy.
