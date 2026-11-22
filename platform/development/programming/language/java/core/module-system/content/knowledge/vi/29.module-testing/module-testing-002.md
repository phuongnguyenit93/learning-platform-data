# Test module-info.java và requires static

Java Platform Module System (JPMS) dùng **module-info.java** để mô tả module: module phụ thuộc vào module nào, package nào được export hoặc open, và module sử dụng hay cung cấp service nào. Vì descriptor quyết định cách chương trình biên dịch và chạy, việc kiểm thử JPMS không nên chỉ dựa vào unit test của class nghiệp vụ. Cần kiểm tra thêm **module contract** và hành vi phân giải dependency trong các cấu hình runtime khác nhau.

Một trường hợp quan trọng là **requires static**: dependency bắt buộc phải có khi biên dịch module, nhưng có thể vắng mặt khi chạy. Nếu chỉ chạy test với tất cả dependency đều có sẵn, rất dễ bỏ sót việc module vẫn vô tình phụ thuộc vào một thư viện vốn được thiết kế là tùy chọn.

Bài này hướng dẫn cách xây dựng một ví dụ modular nhỏ, kiểm tra **module-info.java** sau biên dịch, và viết cả kiểm thử thành công lẫn kiểm thử thất bại có chủ đích cho **requires static**.

## 1. Điều gì cần được kiểm thử trong module-info.java?

Các directive trong descriptor thể hiện hợp đồng giữa module và phần còn lại của ứng dụng:

| Directive | Ý nghĩa | Hướng kiểm thử |
|---|---|---|
| **requires m;** | Dependency bắt buộc; module m phải được resolve khi chạy. | Chạy khi thiếu m phải thất bại trong module resolution. |
| **requires transitive m;** | Truyền khả năng đọc m cho các module đọc module hiện tại. | Compile consumer ngoài module và kiểm tra readability. |
| **requires static m;** | Dependency bắt buộc lúc biên dịch, tùy chọn lúc chạy. | Biên dịch thiếu m phải thất bại; runtime không có m vẫn khởi động nếu code không cần m. |
| **exports p;** | Công bố public API trong package p. | Consumer ngoài module import được API cho phép, không import được package nội bộ. |
| **exports p to m;** | Chỉ công bố package p cho module m. | Consumer m dùng được; một module khác không được quyền. |
| **opens p;** | Mở package p cho deep reflection. | Runtime caller có thể thực hiện reflection phù hợp. |
| **opens p to m;** | Chỉ mở p cho module m. | Test reflection từ module m và module không được phép. |
| **uses S;** | Module tiêu thụ service S. | Kiểm tra descriptor và ServiceLoader trong module consumer. |
| **provides S with P;** | Module đăng ký provider P của service S. | Kiểm tra descriptor và provider discovery/instantiation. |

Một bài test có thể chỉ quan tâm một phần contract, nhưng phải phân biệt kết quả của **compiler**, **module resolver** và **class loader**. Ba tầng này có thể thất bại vì những nguyên nhân khác nhau.

## 2. requires static có ngữ nghĩa chính xác ra sao?

Descriptor:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Có hai tình huống cần hiểu:

**Khi biên dịch:** module **com.acme.annotations** phải được quan sát và phân giải để javac có thể kiểm tra các kiểu mà module ứng dụng tham chiếu. Thiếu dependency sẽ khiến biên dịch module không thành công.

**Khi chạy:** dependency được khai báo bằng **requires static** không bắt buộc phải có trong module configuration. Ứng dụng có thể khởi động mà không có module ấy, miễn là đường thực thi không yêu cầu những kiểu hoặc chức năng runtime đã bị bỏ đi.

So sánh với **requires** thường:

~~~java
module com.acme.app {
    requires com.acme.annotations;
}
~~~

Nếu đổi thành **requires** thường, việc thiếu module **com.acme.annotations** lúc chạy sẽ khiến resolution của module gốc không thành công, ngay cả khi **main** không gọi API của dependency.

**requires static** không tự tạo một implementation dự phòng. Nếu code thực sự nạp class thuộc dependency tùy chọn khi dependency vắng mặt, nó vẫn có thể gặp **ClassNotFoundException**, **NoClassDefFoundError** hoặc lỗi liên quan đến liên kết class. Trách nhiệm thiết kế đường chạy tùy chọn thuộc về ứng dụng.

## 3. Ví dụ: module annotations chỉ dùng lúc biên dịch

Giả sử có hai module:

~~~text
src/
  com.acme.annotations/
    module-info.java
    com/acme/annotations/ApiMarker.java
  com.acme.app/
    module-info.java
    com/acme/app/CompileTimeModel.java
    com/acme/app/Main.java
~~~

Module annotation:

~~~java
// src/com.acme.annotations/module-info.java
module com.acme.annotations {
    exports com.acme.annotations;
}
~~~

Định nghĩa annotation:

~~~java
// src/com.acme.annotations/com/acme/annotations/ApiMarker.java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface ApiMarker {
}
~~~

**RetentionPolicy.CLASS** cho phép annotation xuất hiện trong class file nhưng không được giữ để runtime reflection đọc qua Java reflection API. Nó thích hợp cho ví dụ một annotation hỗ trợ công cụ biên dịch hoặc xử lý bytecode mà ứng dụng không cần trực tiếp sử dụng khi chạy.

Descriptor của app:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Class sử dụng annotation:

~~~java
// src/com.acme.app/com/acme/app/CompileTimeModel.java
package com.acme.app;

import com.acme.annotations.ApiMarker;

@ApiMarker
public final class CompileTimeModel {
}
~~~

Main không phụ thuộc annotation tại runtime:

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Ứng dụng modular khởi động thành công");
    }
}
~~~

Ví dụ này có mục đích cụ thể: **javac cần module annotations khi compile**, còn **Main** có thể chạy ngay cả khi module annotations không được cung cấp lúc runtime.

Trong dự án thực tế, phải xem xét mọi class được nạp trên đường chạy, đặc biệt khi annotation có retention **RUNTIME**, khi framework đọc annotation bằng reflection hoặc khi public method signature nhắc đến kiểu từ dependency tùy chọn.

## 4. Biên dịch cả hai module

Với cấu trúc **src** ở trên, có thể biên dịch vào thư mục **mods**:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.annotations,com.acme.app
~~~

Lệnh biên dịch theo chế độ nhiều module:

- **--module-source-path src**: cho javac biết cấu trúc source theo tên module.
- **-d mods**: chỉ định thư mục output.
- **-m**: chọn các module nguồn sẽ được biên dịch.

Sau biên dịch, cấu trúc chính có dạng:

~~~text
mods/
  com.acme.annotations/
    module-info.class
    com/acme/annotations/ApiMarker.class
  com.acme.app/
    module-info.class
    com/acme/app/CompileTimeModel.class
    com/acme/app/Main.class
~~~

Có thể kiểm tra metadata của module app sau khi đóng gói. Ví dụ đóng gói hai module:

~~~bash
jar --create \
    --file com.acme.annotations.jar \
    -C mods/com.acme.annotations .

jar --create \
    --file com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Lệnh **--main-class** ghi main class vào module metadata khi đóng gói JAR modular. Nếu không sử dụng metadata này, vẫn có thể chạy bằng cú pháp chỉ định rõ main class sau dấu gạch chéo của **-m**.

## 5. Positive compile test: dependency có mặt

Bước kiểm thử đầu tiên là xác minh project compile thành công khi module tùy chọn có mặt ở compile-time.

Ví dụ đã biên dịch cả hai module từ source:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.annotations,com.acme.app
~~~

Nếu module annotation không export package **com.acme.annotations**, app có thể không import được **ApiMarker** dù module đã có trên module path.

Vì vậy, positive test xác nhận đồng thời:

1. Module dependency tồn tại trong phạm vi compilation.
2. Tên trong **requires static** khớp tên module thực tế.
3. Module app được phép đọc dependency ở compile-time.
4. Package annotation được export cho module app.
5. Source code sử dụng annotation được biên dịch thành công.

Nếu test chỉ kiểm tra source có chuỗi **requires static**, nó không xác nhận các điều kiện này. Để có bằng chứng chắc chắn, hãy để javac thực sự biên dịch module consumer.

## 6. Negative compile test: thiếu dependency phải thất bại

Đây là nửa thứ hai của hợp đồng **requires static**. Một dependency tùy chọn **chỉ tùy chọn lúc chạy**, không tùy chọn lúc biên dịch.

Để kiểm thử, compile riêng module app trong một lệnh mà module annotation không có trên module path và cũng không được cung cấp qua module-source-path:

~~~bash
mkdir -p empty-module-path

javac --module-path empty-module-path \
      -d negative-build \
      src/com.acme.app/module-info.java \
      src/com.acme.app/com/acme/app/Main.java \
      src/com.acme.app/com/acme/app/CompileTimeModel.java
~~~

Lệnh trên được kỳ vọng thất bại với diagnostic tương tự:

~~~text
module not found: com.acme.annotations
~~~

Nguyên nhân không phải vì **Main** cần annotation lúc chạy. Nguyên nhân là descriptor yêu cầu **com.acme.annotations** để biên dịch module app.

Với CI, nên kiểm tra:

- Exit code của **javac** khác 0.
- Diagnostic liên quan đến module **com.acme.annotations** không tìm thấy, thay vì một lỗi cú pháp hoặc đường dẫn source sai.

Ví dụ script Bash dùng ý tưởng expected failure:

~~~bash
set +e
javac --module-path empty-module-path \
      -d negative-build \
      src/com.acme.app/module-info.java \
      src/com.acme.app/com/acme/app/Main.java \
      src/com.acme.app/com/acme/app/CompileTimeModel.java \
      > negative-compile.log 2>&1
code=$?
set -e

if [ "$code" -eq 0 ]; then
    echo "FAIL: compile thiếu com.acme.annotations vẫn thành công"
    exit 1
fi

grep -q "com.acme.annotations" negative-compile.log || {
    echo "FAIL: lỗi không liên quan module dependency"
    exit 1
}
~~~

Không nên đánh dấu kiểm thử thành công chỉ vì javac có bất kỳ lỗi nào. Nếu fixture hỏng hoặc lệnh không chạy đúng, phép thử không chứng minh được ngữ nghĩa của **requires static**.

## 7. Runtime test: dependency vắng mặt nhưng app vẫn chạy

Sau khi biên dịch thành công, sao chép **chỉ module app** vào module path dành cho runtime test.

Linux/macOS:

~~~bash
mkdir -p runtime-only
cp -R mods/com.acme.app runtime-only/
~~~

Chạy:

~~~bash
java --module-path runtime-only \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Kết quả mong đợi từ **Main**:

~~~text
Ứng dụng modular khởi động thành công
~~~

Module **com.acme.annotations** không có trong **runtime-only**, nhưng app vẫn được phép khởi động vì dependency đã được khai báo **requires static**.

Để tránh nhầm lẫn giữa classpath và module path, dùng **-m** để chạy named module. Cũng nên giữ riêng thư mục runtime test, thay vì dùng luôn output **mods** chứa cả hai module.

Trên Windows PowerShell, có thể sao chép module bằng:

~~~powershell
New-Item -ItemType Directory -Force -Path runtime-only
Copy-Item -Recurse -Path mods/com.acme.app -Destination runtime-only/
java --module-path runtime-only -m com.acme.app/com.acme.app.Main
~~~

Đây là kiểm thử quan trọng vì chứng minh được hợp đồng runtime: **requires static không biến dependency compile-time thành dependency runtime bắt buộc**.

## 8. Runtime test: dependency có mặt

Cũng cần kiểm thử một môi trường có module optional. Ví dụ:

~~~bash
java --module-path mods \
     --add-modules com.acme.annotations \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Ở đây:

- Module **com.acme.annotations** có mặt trên module path.
- **--add-modules com.acme.annotations** chủ động yêu cầu đưa module này vào tập module gốc khi resolution.
- App vẫn khai báo **requires static**, nên có thể sử dụng dependency nếu nó được resolve trong configuration runtime.

Không nên nhầm **JAR có mặt trên module path** với **module chắc chắn đã được resolve**. Với dependency static, việc có thêm module trong đường dẫn chưa tự bảo đảm mọi code của nó đã tham gia module graph. Nếu ứng dụng muốn dùng tính năng tùy chọn tại runtime, cần thiết kế cách bảo đảm module phù hợp đã được resolve, chẳng hạn chọn root module thích hợp hoặc cấu hình service binding phù hợp.

Có thể in trạng thái để quan sát:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        boolean available = ModuleLayer.boot()
            .findModule("com.acme.annotations")
            .isPresent();

        System.out.println("Optional module resolved: " + available);
    }
}
~~~

Với **runtime-only**, kết quả được kỳ vọng là **false**. Với lệnh có **--add-modules com.acme.annotations**, kết quả được kỳ vọng là **true**.

Việc module được resolve không đồng nghĩa ứng dụng phải trực tiếp dùng annotation bằng reflection. Đây là hai khía cạnh tách biệt: module graph và logic nghiệp vụ của chương trình.

## 9. Kiểm thử descriptor bằng ModuleDescriptor

Ngoài compile và runtime tests, nên kiểm tra trực tiếp descriptor đã biên dịch để xác nhận dependency không vô tình đổi từ static thành bắt buộc.

API **java.lang.module.ModuleFinder** cho phép tìm module trong artifact:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public final class DescriptorTest {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        ModuleReference ref = finder.find("com.acme.app")
            .orElseThrow(() ->
                new AssertionError("Không tìm thấy com.acme.app"));

        ModuleDescriptor descriptor = ref.descriptor();

        ModuleDescriptor.Requires dependency = descriptor.requires()
            .stream()
            .filter(r -> r.name().equals("com.acme.annotations"))
            .findFirst()
            .orElseThrow(() ->
                new AssertionError("Thiếu requires com.acme.annotations"));

        boolean isStatic = dependency.modifiers()
            .contains(ModuleDescriptor.Requires.Modifier.STATIC);

        if (!isStatic) {
            throw new AssertionError(
                "Dependency đã biến thành requires runtime bắt buộc"
            );
        }

        System.out.println("Static dependency contract preserved");
    }
}
~~~

Đây là kiểm thử cấu trúc module descriptor, không cần nạp class nghiệp vụ. Nó kiểm tra:

- Module **com.acme.app** tồn tại trong artifact cần kiểm thử.
- **requires com.acme.annotations** thực sự có trong descriptor.
- Dependency có modifier **STATIC**.

Nếu muốn kiểm tra chính xác contract, có thể kiểm tra thêm modifier **TRANSITIVE** và các directive **exports**, **opens**, **uses**, **provides** theo allowlist của dự án.

Lưu ý: **ModuleDescriptor.requires()** có thể bao gồm dependency **java.base** với modifier **MANDATED** do JPMS bổ sung. Đừng mặc định mọi mục trong tập **requires()** đều được viết trực tiếp trong source **module-info.java**.

## 10. Kiểm thử từ modular JAR cuối cùng

Để xác định artifact phát hành thực sự giữ lại descriptor, nên kiểm tra modular JAR sau packaging:

~~~bash
jar --describe-module --file com.acme.app.jar
~~~

Công cụ sẽ in tên module và các directive. Khi xem kết quả, tìm dependency **com.acme.annotations** và xác nhận nó có tính chất static. Cách trình bày văn bản có thể khác nhau giữa các JDK, nên với kiểm thử tự động cần ưu tiên API **ModuleDescriptor** thay vì chỉ dựa vào chuỗi output của CLI.

Kiểm tra thành phần JAR:

~~~bash
jar --list --file com.acme.app.jar
~~~

Đảm bảo có:

~~~text
module-info.class
com/acme/app/Main.class
com/acme/app/CompileTimeModel.class
~~~

Nếu **module-info.class** bị mất do đóng gói, artifact có thể được coi là automatic module khi đặt trên module path. Automatic module có ngữ nghĩa export/open rộng và dependency graph khác với explicit module. Một kiểm thử chỉ chạy code nghiệp vụ trên classpath có thể không phát hiện sai lệch này.

Kiểm tra loại module bằng descriptor:

~~~java
if (descriptor.isAutomatic() || descriptor.isOpen()) {
    throw new AssertionError(
        "Artifact không còn là explicit module đóng gói theo policy"
    );
}
~~~

Ở đây chính sách của ví dụ yêu cầu explicit module không open. Dự án khác có thể cho phép open module, nhưng phải quyết định trước thay vì bỏ qua thay đổi ngoài dự kiến.

## 11. requires static không bảo vệ code khỏi lỗi runtime nếu sử dụng dependency

Một hiểu nhầm phổ biến là dependency được đánh dấu static sẽ luôn an toàn khi thiếu module ở runtime. Thực tế, chỉ có **module resolution** cho phép vắng mặt; JVM vẫn cần class tương ứng nếu một đường chạy thực sự sử dụng kiểu từ dependency.

Giả sử:

~~~java
package com.acme.app;

import com.acme.annotations.ApiMarker;

public final class OptionalFeature {
    public static Class<?> markerType() {
        return ApiMarker.class;
    }
}
~~~

Khi runtime thiếu **com.acme.annotations**, code gọi **OptionalFeature.markerType()** có thể thất bại trong quá trình nạp hoặc liên kết class vì tham chiếu đến **ApiMarker** không thể được giải quyết.

Vì vậy, khi dùng **requires static** cho một thư viện tùy chọn thực sự có chức năng runtime, cần:

1. Đặt code sử dụng dependency vào một nhánh chỉ chạy khi tính năng được bật và dependency hiện diện.
2. Tránh khiến main class, static initializer hoặc public API bắt buộc phải resolve kiểu tùy chọn ngay khi ứng dụng khởi động.
3. Cân nhắc tách adapter dành cho optional dependency sang module riêng nếu ranh giới phức tạp.
4. Kiểm thử cả **không có dependency** và **có dependency** bằng các JVM mới, với module path được kiểm soát.

Đặc biệt, nếu annotation có retention **RUNTIME** và framework cần đọc annotation để xử lý nghiệp vụ, module annotation không còn đơn thuần là compile-only. Khi đó phải đưa dependency thích hợp vào runtime và kiểm thử xử lý thực tế.

## 12. Phân biệt requires static và requires transitive

Hai modifier giải quyết hai nhu cầu khác nhau.

**requires static** cho phép dependency vắng mặt lúc chạy:

~~~java
module com.acme.library {
    requires static com.acme.optional;
}
~~~

**requires transitive** truyền khả năng đọc dependency cho module tiêu thụ:

~~~java
module com.acme.library {
    requires transitive com.acme.api;
}
~~~

Trong Java, các modifier có thể kết hợp theo quy tắc ngôn ngữ, nhưng đừng sử dụng kết hợp chỉ để khiến build thành công. Hãy quyết định liệu dependency có thực sự là một phần của API công khai hay chỉ phục vụ biên dịch.

Khi một kiểu từ dependency xuất hiện trong public signature, consumer thường cần biết module chứa kiểu để biên dịch. Nếu dependency đó có thể biến mất lúc chạy, chính sách compatibility phải được xem xét cẩn thận. Một module chứa API public phụ thuộc sâu vào kiểu runtime tùy chọn có thể làm consumer gặp lỗi mà **requires static** không thể tự xử lý.

Test module descriptor có thể kiểm tra đồng thời modifier **STATIC** và **TRANSITIVE** nếu contract thiết kế yêu cầu, nhưng không nên suy luận modifier nào cũng tương đương nhau.

## 13. Negative runtime test: đổi sang requires thường phải thất bại khi thiếu module

Để minh họa sự khác biệt rõ ràng, có thể chuẩn bị một phiên bản thử nghiệm của descriptor:

~~~java
module com.acme.app {
    requires com.acme.annotations;
}
~~~

Biên dịch lại app với dependency đầy đủ. Sau đó chạy trong thư mục **runtime-only** chỉ chứa app:

~~~bash
java --module-path runtime-only \
     -m com.acme.app/com.acme.app.Main
~~~

Kết quả được kỳ vọng là lỗi trong khởi tạo module layer hoặc module resolution, thường có thông báo tương tự:

~~~text
Module com.acme.annotations not found, required by com.acme.app
~~~

Đây là test đối chứng để chứng minh khác biệt giữa **requires** thường và **requires static**. Không nên dùng phiên bản descriptor đã sửa như bản phát hành thực tế nếu thiết kế ban đầu yêu cầu optional runtime dependency.

Trong CI, hãy quản lý fixture đối chứng riêng hoặc tạo module test tạm thời để không vô tình thay đổi descriptor của artifact đang phát hành.

## 14. Kiểm thử khi sử dụng JUnit

Nếu sử dụng JUnit để kiểm tra descriptor, test có thể đọc module metadata bằng Java API thay vì dựa vào output của công cụ dòng lệnh:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class ModuleContractTest {

    @Test
    void annotationsDependencyMustRemainStatic() {
        ModuleDescriptor descriptor = ModuleFinder
            .of(Path.of("mods"))
            .find("com.acme.app")
            .orElseThrow()
            .descriptor();

        var dependency = descriptor.requires()
            .stream()
            .filter(r -> r.name().equals("com.acme.annotations"))
            .findFirst()
            .orElseThrow();

        assertTrue(dependency.modifiers().contains(
            ModuleDescriptor.Requires.Modifier.STATIC
        ));

        assertFalse(descriptor.isAutomatic());
    }
}
~~~

Đây là unit test của metadata contract. Cần kết hợp với **integration tests sử dụng javac và java thật**, vì chỉ thấy modifier STATIC không chứng minh toàn bộ ứng dụng sẽ chạy ổn khi dependency vắng mặt.

Tùy cách JUnit chạy trên classpath hoặc module path, module test có thể cần cấu hình riêng. Tránh để những flag như **--add-reads**, **--add-exports** hoặc **--patch-module** vô tình che giấu lỗi mà phép thử định phát hiện.

## 15. Maven và Gradle có thay thế requires static không?

Build tool quản lý artifact dependency; JPMS quản lý named module dependency. Đây là hai tầng khác nhau.

Trong Gradle, dependency chỉ phục vụ biên dịch thường được cấu hình bằng **compileOnly**:

~~~groovy
dependencies {
    compileOnly("com.acme:annotations:1.0")
}
~~~

Trong Maven, một dependency không được đóng gói như runtime dependency có thể dùng scope như **provided** trong tình huống phù hợp:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>annotations</artifactId>
    <version>1.0</version>
    <scope>provided</scope>
</dependency>
~~~

Tuy nhiên, **compileOnly** hoặc **provided** không tự viết **requires static** vào descriptor. Ngược lại, **requires static** cũng không tự tải dependency vào classpath/module path khi chạy build.

Cần đồng bộ:

- Build tool phải cung cấp artifact đúng để javac compile module.
- **module-info.java** phải khai báo tên JPMS của module, không phải Maven/Gradle artifact coordinates.
- Runtime packaging phải cố ý quyết định có đưa dependency tùy chọn vào không.
- Integration tests phải chạy theo module path thực tế, không chỉ classpath của IDE.

Nếu artifact chỉ có **Automatic-Module-Name** hoặc tên module được suy ra từ JAR, hãy kiểm tra tên module thực tế bằng **jar --describe-module** trước khi viết **requires static**.

## 16. Kiểm tra module graph khi chạy

Tùy chọn **--show-module-resolution** giúp quan sát những module được chọn khi khởi động:

~~~bash
java --show-module-resolution \
     --module-path runtime-only \
     -m com.acme.app/com.acme.app.Main
~~~

Có thể so sánh với cấu hình chủ động resolve optional module:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.annotations \
     -m com.acme.app/com.acme.app.Main
~~~

Khi kiểm tra output, hãy chú ý các root module, **requires** và vị trí module. Đừng kết luận một module đã được resolve chỉ vì JAR xuất hiện trong thư mục được chỉ định bởi **--module-path**.

Có thể dùng:

~~~bash
java --module-path mods --list-modules
~~~

để quan sát các module có thể được launcher tìm thấy, nhưng lệnh này không tương đương với việc xác nhận mọi module đã được đưa vào runtime configuration của ứng dụng. Để kiểm tra module thực sự trong boot layer, dùng **ModuleLayer.boot().findModule(...)** như ví dụ ở trên.

## 17. Ma trận kiểm thử nên có trong CI

| Kịch bản | Dependency compile-time | Dependency runtime | Kết quả mong đợi |
|---|---|---|---|
| A. Compile đầy đủ | Có | Chưa áp dụng | **javac** thành công. |
| B. Compile thiếu module static | Không | Chưa áp dụng | **javac** thất bại đúng vì thiếu module. |
| C. Chạy tối giản | Đã biên dịch với module | Không | Main không sử dụng dependency vẫn khởi động. |
| D. Chạy có module tùy chọn | Đã biên dịch với module | Có và được resolve | App khởi động, module tùy chọn quan sát được. |
| E. Đổi descriptor thành requires thường | Có | Không | Resolution thất bại khi thiếu module. |
| F. Đọc artifact đã đóng gói | Có | Không phụ thuộc | Descriptor có đúng **STATIC**, tên module và loại module. |
| G. Gọi tính năng thật sự cần module tùy chọn | Có | Không | Có thể thất bại; code phải xử lý theo thiết kế tính năng. |

Chạy matrix bằng các tiến trình JVM riêng để hạn chế ảnh hưởng từ class loader, state và module path của test runner. Khi test một artifact phát hành, hãy trỏ đến đúng JAR đã đóng gói thay vì một bản build khác trong thư mục IDE.

Đối với expected-failure tests, kiểm tra cả exit code và nguyên nhân cụ thể. Một lệnh thất bại vì thiếu Java executable hoặc đường dẫn sai không phải bằng chứng cho contract **requires static**.

## 18. Những lỗi và nhầm lẫn phổ biến

| Triệu chứng | Nguyên nhân cần xem xét | Cách xử lý |
|---|---|---|
| **module not found** trong javac | Module được khai báo **requires static** vắng mặt ở compile-time. | Bổ sung đúng named module vào đường dẫn biên dịch. |
| Module app chạy được dù thiếu dependency | Đây có thể là hành vi đúng của **requires static**. | Kiểm tra đường chạy không sử dụng kiểu runtime tùy chọn. |
| Runtime có JAR nhưng **findModule** trả empty | JAR có mặt trên module path nhưng module chưa được resolve. | Cấu hình root/module resolution phù hợp, ví dụ **--add-modules**. |
| **NoClassDefFoundError** khi gọi optional feature | Code runtime cần kiểu thuộc dependency đã bỏ đi. | Thiết kế ranh giới optional feature hoặc cung cấp dependency. |
| Test pass trong IDE nhưng lỗi sau đóng gói | IDE dùng classpath hoặc module path khác artifact. | Chạy test trên modular JAR cuối cùng bằng **-m**. |
| **requires static** biến thành **requires** | Descriptor bị sửa hoặc build dùng artifact khác. | Đọc **ModuleDescriptor.Requires.Modifier.STATIC** từ JAR. |
| Automatic module thay explicit module | Descriptor bị thiếu hoặc đóng gói không đúng. | Kiểm tra **module-info.class**, **isAutomatic()**. |
| Negative test báo thành công vì lỗi cú pháp | Script chỉ kiểm tra exit code khác 0. | Xác nhận diagnostic nhắc đúng dependency/module. |

## 19. Checklist thực hành

- Xác định dependency nào chỉ bắt buộc lúc compile và thật sự có thể thiếu tại runtime.
- Khai báo **requires static** bằng tên JPMS module chính xác trong **module-info.java**.
- Kiểm tra package dependency được export đủ cho code sử dụng ở compile-time.
- Compile có dependency và xác nhận thành công.
- Compile thiếu dependency và xác nhận thất bại đúng vì module không tìm thấy.
- Chạy module app bằng **-m** khi dependency hoàn toàn vắng mặt trên runtime module path.
- Chạy với dependency đã được resolve và kiểm tra hành vi cần thiết.
- Đọc descriptor của modular JAR sau packaging bằng **ModuleFinder/ModuleDescriptor**.
- Xác nhận modifier **STATIC** không bị mất, module không vô tình thành automatic.
- Chạy runtime test có và không có dependency trong các tiến trình JVM riêng.
- Không đánh đồng build tool scope với chỉ thị **requires static**.
- Nếu code dùng dependency tại runtime, thêm kiểm thử tính năng hoặc tách adapter để tránh lỗi nạp class khi module vắng mặt.

**Test module-info.java và requires static** là kiểm thử một hợp đồng phụ thuộc ở cả hai thời điểm: compile và runtime. Một module được thiết kế đúng phải có đủ dependency cho javac, giữ modifier **STATIC** trong artifact và có đường chạy hợp lệ khi optional module không xuất hiện. Kết hợp descriptor tests, expected-failure compilation tests và runtime tests ở hai cấu hình sẽ giúp phát hiện sớm lỗi JPMS trước khi phát hành.