# Rà soát dependency còn nằm ngoài module path

Khi chuyển một ứng dụng Java sang Java Platform Module System (JPMS), không phải mọi thư viện đều tự động trở thành named module. Một ứng dụng có thể đã có `module-info.java`, nhưng một số dependency vẫn được đặt trên **classpath** thay vì **module path**. Những thư viện trên classpath thuộc unnamed module; chúng không có module descriptor tường minh và không tham gia module graph theo cách của explicit module.

Việc rà soát dependency còn nằm ngoài module path giúp phát hiện các thư viện chưa được modular hóa, cấu hình build chưa nhất quán hoặc dependency runtime bị bỏ sót. Đây là bước quan trọng để ứng dụng có thể kiểm soát dependency và quyền truy cập đúng theo JPMS.

## 1. Classpath, module path và unnamed module

Trước JPMS, Java thường tìm class và thư viện qua classpath:

~~~bash
java -cp "app.jar:libs/*" com.example.app.Main
~~~

Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;libs/*" com.example.app.Main
~~~

Khi một ứng dụng chạy theo cách truyền thống này, các class và JAR trên classpath được nạp vào **unnamed module** tương ứng với class loader. Unnamed module không có tên module ổn định trong `module-info.java`; nó là một phần của cơ chế tương thích classpath.

JPMS bổ sung module path để tìm các named module:

~~~bash
java --module-path "mods:libs" -m com.example.app/com.example.app.Main
~~~

Trong ví dụ trên:

- `--module-path` chỉ các thư mục hoặc JAR chứa module.
- `-m` chỉ module và class main cần khởi chạy.
- Module có descriptor tường minh hoặc automatic module có thể được tìm thấy trên module path.

Hai cơ chế có thể cùng xuất hiện trong một lệnh chạy:

~~~bash
java --module-path mods --class-path "legacy/*" -m com.example.app/com.example.app.Main
~~~

Trong đó các JAR ở `legacy/*` vẫn thuộc unnamed module; chúng không tự trở thành named module chỉ vì ứng dụng chính được khởi chạy bằng `-m`.

## 2. Ba trạng thái thường gặp của dependency

Khi rà soát một JAR, cần xác định nó đang thuộc trường hợp nào.

### 2.1. Explicit named module

Đây là thư viện có module descriptor tường minh, thường được tạo từ `module-info.java` và đóng gói thành `module-info.class`.

Ví dụ:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

JAR modular có thể được đặt trên module path. Module khác có thể khai báo dependency:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Đây là trạng thái cung cấp khả năng kiểm soát dependency và package rõ ràng nhất.

### 2.2. Automatic module

Một JAR không có `module-info.class` khi được đặt trên module path có thể được xử lý như **automatic module**. Tên module được suy ra từ tên JAR, hoặc lấy từ thuộc tính `Automatic-Module-Name` trong manifest nếu thư viện cung cấp thuộc tính đó.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

Module ứng dụng có thể khai báo:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Automatic module là cầu nối hỗ trợ thư viện cũ tham gia module path. Nó có cách đọc module và export package rộng hơn explicit module, vì vậy chưa tạo ra mức encapsulation chặt như một descriptor được thiết kế chủ động.

Nếu thư viện không thể sửa ngay, automatic module thường là bước chuyển tiếp hữu ích. Với thư viện do nhóm phát triển sở hữu, nên cân nhắc bổ sung module descriptor tường minh khi đã xác định được API và dependency.

### 2.3. Dependency trên classpath (unnamed module)

JAR nằm trên classpath thuộc unnamed module. Nó không có tên để module khác viết trong directive `requires`.

Ví dụ:

~~~bash
java --module-path mods --class-path "legacy/old-client.jar" \
     -m com.example.app/com.example.app.Main
~~~

Trong trường hợp này, `old-client.jar` nằm ngoài module path. Named module `com.example.app` không tự động đọc unnamed module. Vì vậy, code trong module có thể gặp lỗi khi import hoặc sử dụng class đến từ thư viện đó.

Không thể viết:

~~~java
module com.example.app {
    requires unnamed;
}
~~~

`unnamed` không phải tên module hợp lệ để dùng trong `requires`. Nếu muốn sử dụng thư viện theo module path, cần đưa nó vào module path dưới dạng automatic module hoặc explicit module; nếu buộc phải giữ classpath, cần cân nhắc cơ chế tương thích như `--add-reads` ở phần sau.

## 3. Vì sao dependency ngoài module path gây vấn đề?

Một named module chỉ có thể sử dụng kiểu từ module mà nó đọc được, đồng thời package cần truy cập phải được module kia export phù hợp.

Nếu thư viện vẫn ở unnamed module:

- Named module không có quan hệ `requires` tường minh tới thư viện đó.
- Dependency không xuất hiện như một named module trong module graph.
- Khó kiểm soát package nào của thư viện được công bố.
- Việc kiểm tra dependency bằng công cụ JPMS không thể hiện đầy đủ trạng thái của thư viện trên classpath.
- Build có thể biên dịch theo classpath nhưng runtime lại khởi chạy bằng module path khác, dẫn đến lỗi thiếu class hoặc không đọc được package.

Một lỗi thường gặp là source có import:

~~~java
import com.vendor.legacy.Client;
~~~

nhưng thư viện chứa `com.vendor.legacy.Client` chỉ được thêm vào classpath. Khi biên dịch module, compiler có thể báo package không tồn tại hoặc không được nhìn thấy. Nguyên nhân cần kiểm tra là vị trí dependency và khả năng đọc module, không chỉ tên import.

## 4. Kiểm kê dependency từ build và lệnh chạy

Trước khi thay đổi cấu hình, hãy lập danh sách dependency thực tế ở cả compile time và runtime.

Với Gradle, có thể xem dependency graph của project:

~~~bash
./gradlew :app:dependencies
~~~

Để xem một configuration cụ thể:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn -pl app dependency:tree
~~~

Các báo cáo này cho biết thư viện nào được khai báo trực tiếp hoặc gián tiếp và configuration nào chứa chúng. Tuy nhiên, dependency report của build tool chưa đủ để chứng minh một JAR đang nằm trên module path. Cần đối chiếu với cách plugin/build task cấu hình compiler và JVM.

Khi chạy ứng dụng, kiểm tra đầy đủ các tham số:

- `--module-path` hoặc `-p`: các module path entries.
- `--class-path` hoặc `-cp`: các classpath entries.
- `-m` hoặc `--module`: module main được khởi chạy.
- Các tham số bổ sung như `--add-reads`, `--add-modules`, `--patch-module` nếu có.

Đừng chỉ nhìn vào `build.gradle` hoặc `pom.xml`; lệnh chạy thực tế, cấu hình IDE, script triển khai và container command cũng có thể bổ sung classpath/module path riêng.

## 5. Dùng công cụ JDK để xác định trạng thái module

### 5.1. Kiểm tra một JAR bằng jar --describe-module

Lệnh:

~~~bash
jar --describe-module --file libs/legacy-client.jar
~~~

Có thể cho biết:

- JAR có module descriptor tường minh hay không.
- Tên module được suy ra nếu đây là automatic module.
- Những package được export hoặc các service được khai báo trong descriptor.

Nếu JAR không có descriptor và được đặt trên classpath, việc chạy lệnh kiểm tra không biến nó thành named module. Hãy xem kết quả cùng vị trí thực tế của JAR trong lệnh chạy.

### 5.2. Phân tích dependency bằng jdeps

`jdeps` phân tích dependency ở cấp class, package và module. Một số lệnh hữu ích:

~~~bash
# Xem dependency ở cấp module của một JAR
jdeps --list-deps libs/legacy-client.jar

# Phân tích dependency với các module có trên module path
jdeps --module-path mods:libs --check com.example.app

# Sinh module-info.java mẫu để hỗ trợ chuyển đổi một JAR
jdeps --generate-module-info generated-modules libs/legacy-client.jar
~~~

Tùy chọn và kết quả cụ thể phụ thuộc phiên bản JDK. File descriptor do công cụ sinh ra là điểm khởi đầu để xem xét; cần kiểm tra lại tên module, package export, dependency và các yêu cầu reflection trước khi dùng trong sản phẩm.

`jdeps` cũng có thể báo dependency tới JDK internal API hoặc dependency không tìm thấy. Hãy đọc kỹ thông báo và cung cấp đủ classpath/module path khi phân tích để tránh kết luận thiếu dữ liệu.

### 5.3. Quan sát module resolution lúc runtime

Có thể yêu cầu JVM in thông tin module được phân giải:

~~~bash
java --show-module-resolution \
     --module-path mods:libs \
     -m com.example.app/com.example.app.Main
~~~

Thông tin này giúp xác nhận module nào được tìm thấy, module nào được yêu cầu và module nào tham gia module graph. Nếu một dependency chỉ nằm trên classpath, hãy đối chiếu với tham số `--class-path` để nhận diện nó thuộc unnamed module.

### 5.4. Xem module đang được JVM nhận diện

Có thể liệt kê module trong runtime image:

~~~bash
java --list-modules
~~~

Lệnh này chủ yếu hữu ích để xem các module nền tảng và module trong runtime image. Nó không thay thế việc kiểm tra toàn bộ dependency bên ngoài mà ứng dụng đưa vào khi khởi chạy.

## 6. Quy trình rà soát một dependency cụ thể

Với mỗi JAR nghi ngờ còn nằm ngoài module path, thực hiện các bước:

1. **Xác định artifact:** ghi tên JAR, phiên bản, nguồn khai báo và lý do ứng dụng cần nó.
2. **Xác định configuration:** kiểm tra dependency xuất hiện trong compile classpath, runtime classpath hay cả hai.
3. **Xác định vị trí lúc chạy:** tìm JAR trong `--module-path`, `--class-path`, thư mục plugin hoặc class loader riêng.
4. **Kiểm tra descriptor:** dùng `jar --describe-module` để xác định explicit module, automatic module hoặc JAR truyền thống.
5. **Kiểm tra tên module:** so sánh tên được công bố với tên trong `requires`; không tự đoán tên từ tên file nếu công cụ đã cung cấp tên chính thức.
6. **Kiểm tra dependency bắc cầu:** xem thư viện đó còn cần JAR nào khác và các dependency ấy đang ở đâu.
7. **Kiểm tra service và reflection:** nếu thư viện dùng SPI, `ServiceLoader`, reflection hoặc framework injection, kiểm tra cấu hình tương ứng khi chuyển vị trí.
8. **Đối chiếu compile và runtime:** bảo đảm cùng một mô hình dependency được áp dụng ở cả hai giai đoạn.

Có thể ghi kết quả kiểm kê theo bảng:

| Dependency | Vị trí hiện tại | Trạng thái module | Hướng xử lý |
|---|---|---|---|
| `catalog-api.jar` | Module path | Explicit module | Giữ `requires` tương ứng |
| `legacy-client.jar` | Classpath | Unnamed module | Đánh giá automatic hoặc explicit module |
| `old-json.jar` | Module path | Automatic module | Lập kế hoạch modular hóa |
| `logging.jar` | Classpath | Unnamed module | Kiểm tra API, runtime và cách nạp |

Đây là ví dụ minh họa; trạng thái thực tế phải lấy từ lệnh chạy và nội dung artifact của dự án.

## 7. Cách đưa dependency vào module path

Có nhiều hướng xử lý, tùy quyền kiểm soát đối với thư viện và khả năng tương thích.

### 7.1. Ưu tiên explicit module khi có thể

Nếu nhóm phát triển sở hữu source của thư viện, hãy tạo `module-info.java`:

~~~java
module com.example.legacy.client {
    requires java.net.http;

    exports com.example.legacy.client.api;
}
~~~

Sau khi biên dịch, JAR cần chứa `module-info.class`. Khi đó có thể đặt JAR trên module path và khai báo:

~~~java
module com.example.app {
    requires com.example.legacy.client;
}
~~~

Hãy chỉ export package API cần công bố. Những package nội bộ có thể được giữ kín để bảo vệ encapsulation.

### 7.2. Dùng automatic module làm bước chuyển tiếp

Nếu chưa thể sửa source của thư viện, có thể đưa JAR không có descriptor lên module path. Java sẽ xử lý nó như automatic module.

Ví dụ:

~~~bash
java --module-path "mods:libs/legacy-client.jar" \
     -m com.example.app/com.example.app.Main
~~~

Sau đó module ứng dụng khai báo tên automatic module thực tế:

~~~java
module com.example.app {
    requires com.example.legacy.client;
}
~~~

Tên minh họa trên chỉ đúng nếu manifest hoặc tên JAR thực sự tạo ra tên module đó. Hãy xác nhận bằng:

~~~bash
jar --describe-module --file libs/legacy-client.jar
~~~

Nếu có quyền thay đổi thư viện, thuộc tính `Automatic-Module-Name` trong manifest giúp giữ tên module ổn định qua những lần đổi tên file JAR. Automatic module hỗ trợ migration nhưng vẫn có mức encapsulation rộng, vì vậy nên xem đây là trạng thái chuyển tiếp khi phù hợp.

### 7.3. Giữ dependency trên classpath như một ngoại lệ có kiểm soát

Trong giai đoạn chuyển đổi, đôi khi cần giữ một thư viện trên classpath. Named module không đọc unnamed module theo mặc định. Có thể dùng tùy chọn tương thích:

~~~bash
java --module-path mods \
     --class-path "legacy/old-client.jar" \
     --add-reads com.example.app=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

`--add-reads com.example.app=ALL-UNNAMED` bổ sung quan hệ readability từ module được chỉ định tới unnamed module. Nó có thể hỗ trợ trường hợp cần tiếp tục dùng classpath trong quá trình migration.

Đây là một ngoại lệ cần quản lý cẩn thận:

- Nó không biến JAR trên classpath thành named module.
- Nó không tạo module descriptor cho thư viện.
- Dependency vẫn nằm ngoài module graph tường minh.
- Các package của unnamed module có tính mở rộng truy cập rộng hơn explicit module.
- Build và runtime phải truyền cùng chính sách phù hợp; cấu hình ở một giai đoạn không tự động áp dụng cho giai đoạn khác.

Không nên thêm `ALL-UNNAMED` cho mọi module chỉ để làm hết lỗi. Hãy giới hạn đúng module cần tương thích và lập kế hoạch loại bỏ ngoại lệ khi thư viện đã được modular hóa hoặc thay thế.

## 8. Kiểm tra dependency bắc cầu và runtime

Một dependency có thể đã nằm trên module path nhưng các dependency mà nó cần vẫn còn trên classpath hoặc bị thiếu ở runtime. Vì vậy, kiểm tra một JAR đơn lẻ là chưa đủ.

Ví dụ:

~~~text
app
  └── requires legacy.client
          ├── requires java.net.http
          └── uses legacy.spi.Transport
                  └── provider nằm trong transport.plugin.jar
~~~

Hãy kiểm tra:

- Module descriptor của thư viện khai báo những `requires` nào.
- Dependency đó có mặt trên module path ở compile time và runtime không.
- Các provider cần thiết có nằm trong module layer mà ứng dụng tìm kiếm không.
- Thư viện có gọi reflection vào package nội bộ không; nếu có, cần xác định chính xác package và module cần `opens`.
- Có cùng một thư viện bị đưa vào cả classpath và module path hay không.

Việc trùng một artifact ở cả hai nơi có thể gây nhầm lẫn về class loader, module identity hoặc phiên bản class được nạp. Nên loại bỏ bản khai báo trùng sau khi xác định đúng vị trí cần dùng.

## 9. Đồng bộ cấu hình Gradle/Maven với JPMS

Build tool quản lý artifact và classpath/module path, còn JPMS kiểm soát readability và encapsulation. Hai tầng phải nhất quán.

Với Gradle, kiểm tra dependency report:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Kiểm tra thêm cấu hình Java compile và task chạy ứng dụng để biết dependency được đưa vào classpath hay module path. Gradle Java plugin có cơ chế suy luận module path cho source modular; hãy xác nhận cấu hình plugin và task thực tế thay vì giả định mọi configuration đều tự chuyển đúng.

Với Maven, xem dependency tree và cấu hình compiler/plugin/exec tương ứng:

~~~bash
mvn -pl app dependency:tree
~~~

Không sửa `module-info.java` chỉ để che lỗi cấu hình build. Nếu dependency thuộc module path, hãy bảo đảm build tool cung cấp đúng module; nếu cố ý giữ classpath, ghi rõ ngoại lệ và thiết lập readability tương ứng ở nơi cần thiết.

## 10. Những lỗi thường gặp

**Source import được thư viện nhưng compiler báo package không tồn tại.** Kiểm tra JAR có thực sự nằm trên compile path được dùng cho module hay không; xác định nó đang ở classpath hay module path.

**`requires` báo không tìm thấy module.** Kiểm tra tên module bằng `jar --describe-module`, vị trí module path và dependency configuration.

**Biên dịch thành công nhưng runtime báo thiếu class.** Compile path và runtime path có thể khác nhau. Kiểm tra tham số khởi chạy, container script, IDE run configuration và dependency runtime.

**Chuyển JAR sang module path nhưng phát sinh lỗi truy cập package.** Nếu là explicit module, package có thể chưa được export; nếu framework dùng reflection, có thể cần `opens` có giới hạn.

**Dùng tên file làm tên module.** Tên module có thể bị chuẩn hóa từ tên JAR hoặc được khai báo trong manifest. Luôn kiểm tra tên mà JDK nhận diện.

**Chuyển dependency thành automatic module nhưng quên dependency của nó.** Kiểm tra cả dependency bắc cầu và provider/service liên quan.

**Thêm `--add-reads` nhưng nghĩ dependency đã modular hóa.** Tùy chọn này chỉ bổ sung readability tới unnamed module; JAR vẫn nằm trên classpath.

## 11. Checklist rà soát

Khi rà soát một ứng dụng modular, hãy kiểm tra lần lượt:

1. Danh sách dependency trực tiếp và bắc cầu ở compile time, runtime.
2. Vị trí từng JAR trong lệnh chạy: module path, classpath hoặc class loader riêng.
3. Trạng thái của từng JAR: explicit module, automatic module hay thư viện trên classpath.
4. Tên module thực tế và các directive `requires` tương ứng.
5. Các dependency vẫn nằm trong unnamed module và lý do chưa chuyển đổi.
6. Cấu hình `--add-reads ...=ALL-UNNAMED` nếu có, phạm vi áp dụng và kế hoạch loại bỏ.
7. Các package cần export hoặc opens và module đích được phép truy cập.
8. Provider/service có được đưa vào đúng module layer hay không.
9. Sự nhất quán giữa compile path và runtime path.
10. Kết quả kiểm tra bằng `jar --describe-module`, `jdeps` và `--show-module-resolution` khi phù hợp.

Rà soát dependency ngoài module path là công việc kiểm tra cả artifact, build configuration và lệnh chạy. Khi phân biệt được explicit module, automatic module và unnamed module, bạn có thể chuyển đổi từng dependency có kiểm soát, giữ tương thích cần thiết và từng bước đưa ứng dụng về một module graph rõ ràng.
