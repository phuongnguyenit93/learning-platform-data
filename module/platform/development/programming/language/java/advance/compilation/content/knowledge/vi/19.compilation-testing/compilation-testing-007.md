# Kiểm thử thiếu phụ thuộc, xung đột kiểu và cấu hình mô-đun trong Java

## 1. Mục tiêu và phạm vi

Một thay đổi nhỏ trong **classpath**, phiên bản thư viện hoặc cấu hình **Java Platform Module System (JPMS)** có thể làm cho cùng một mã nguồn Java biên dịch thành công ở môi trường này nhưng thất bại ở môi trường khác. Kiểm thử biên dịch cho các trường hợp này cần chứng minh cả hai chiều: cấu hình **đúng phải được chấp nhận**, còn cấu hình **sai có chủ đích phải bị từ chối vì đúng nguyên nhân**.

Sau bài này, người học có thể:

- Phân biệt thiếu phụ thuộc tại thời điểm biên dịch với lỗi tải lớp khi chạy.
- Thiết kế cặp ca có/không có thư viện cần thiết trên **--class-path**.
- Kiểm tra xung đột kiểu do hai phiên bản API không tương thích và phân biệt với trùng tên lớp hoặc tên đơn giản gây mơ hồ.
- Thiết kế ca JPMS cho **requires**, **exports**, **--module-path** và **--module-source-path**.
- Viết bộ chạy tự động gọi **javac**, đọc exit code và thông báo chẩn đoán, cô lập từng lượt compile, xác nhận ca âm không “PASS giả”.
- Xác định giới hạn của bài kiểm thử: không suy ra lỗi runtime, dependency resolution của Gradle/Maven hay tính tương thích nhị phân chỉ từ kết quả một lượt compile.

Trong toàn bài, sử dụng **JDK 17 trở lên** với tùy chọn **--release 17**. Biên dịch bằng JDK mới hơn vẫn kiểm tra cú pháp/API chuẩn Java 17; đường dẫn và JAR thư viện do bài thực hành tự tạo, không phụ thuộc dịch vụ bên ngoài.

## 2. Mô hình kiểm thử: thay đổi một điều kiện tại mỗi ca

Một phép thử đáng tin cần cố định những biến không liên quan và chỉ thay đổi điều kiện muốn kiểm tra:

| Nhóm | Ca phải được chấp nhận (positive) | Ca phải bị từ chối (negative) | Nguyên nhân kỳ vọng |
| --- | --- | --- | --- |
| Thiếu phụ thuộc | Thư viện API nằm trên classpath | Bỏ JAR đó khỏi classpath | Không phân giải được package/symbol |
| Xung đột chữ ký API | Client biên dịch với API v1 trả String | Đổi sang API v2 trả int | Kiểu trả về không phù hợp với client |
| Tên kiểu mơ hồ | Chỉ định rõ java.util.Date | Import hai package có Date rồi dùng Date không đầy đủ | Tên kiểu không xác định duy nhất |
| JPMS requires | Module ứng dụng khai báo requires thư viện | Bỏ requires | Module ứng dụng không đọc module chứa API |
| JPMS exports | Module thư viện exports package API | Bỏ exports | Package tồn tại nhưng không được export tới module gọi |
| Module path | Module được cung cấp trên đường dẫn mô-đun hợp lệ | Bỏ/thay đường dẫn chứa module khi biên dịch tách rời | Module bắt buộc không được tìm thấy |

**Kết quả PASS không đồng nghĩa “có lỗi bất kỳ”.** Với ca âm, cần quan sát **javac thất bại** và lỗi liên quan đúng quy tắc đang kiểm tra. Nếu mã đã sai từ trước do tên tệp, dấu ngoặc, encoding, dependency phụ khác hoặc sai lệnh javac, kết quả từ chối không chứng minh giả thuyết cần thử.

Mỗi ca nên có metadata gồm **ID, mã nguồn, JDK/compiler options, classpath/module path, kỳ vọng ACCEPT/REJECT, nguyên nhân dự kiến, kết quả thực tế và diagnostic**. Đối với test nhiều JDK, cố định **--release** và ghi lại JDK vendor/version vì một số thông báo và mã chẩn đoán là chi tiết triển khai của javac.

## 3. Classpath: kiểm thử phụ thuộc có mặt và bị thiếu

### 3.1. Ba nguồn Java tối thiểu

Tạo cấu trúc:

~~~text
source/
  v1/com/example/api/VersionApi.java
  v2/com/example/api/VersionApi.java
  app/com/example/app/Client.java
~~~

**source/v1/com/example/api/VersionApi.java** (API hợp lệ cho client):

~~~java
package com.example.api;

public final class VersionApi {
    private VersionApi() {}

    public static String version() {
        return "v1";
    }
}
~~~

**source/v2/com/example/api/VersionApi.java** (cùng tên API nhưng chữ ký đã thay đổi):

~~~java
package com.example.api;

public final class VersionApi {
    private VersionApi() {}

    public static int version() {
        return 2;
    }
}
~~~

**source/app/com/example/app/Client.java** (giữ nguyên trong mọi lượt compile):

~~~java
package com.example.app;

import com.example.api.VersionApi;

public final class Client {
    public static String value() {
        return VersionApi.version();
    }
}
~~~

Khi dùng API v1, giá trị trả về là **String** và client hợp lệ. Với API v2, **VersionApi.version()** trả **int**, nên biểu thức không gán được cho **String**. Khi bỏ JAR, package **com.example.api** không xuất hiện trên đường dẫn phụ thuộc, nên trình biên dịch không phân giải được import.

### 3.2. Xây hai thư viện độc lập

Trong terminal tại thư mục chứa **source/**, tạo các thư mục đầu ra rồi thực hiện:

~~~bash
mkdir -p out/v1 out/v2 out/dep-ok out/no-dep out/type-conflict

javac --release 17 -encoding UTF-8 -d out/v1 source/v1/com/example/api/VersionApi.java
jar --create --file out/v1.jar -C out/v1 .

javac --release 17 -encoding UTF-8 -d out/v2 source/v2/com/example/api/VersionApi.java
jar --create --file out/v2.jar -C out/v2 .
~~~

Đoạn **mkdir -p** dành cho Linux/macOS. Trong PowerShell, tạo thư mục tương đương bằng lệnh:

~~~powershell
New-Item -ItemType Directory -Force -Path out/v1,out/v2,out/dep-ok,out/no-dep,out/type-conflict | Out-Null
~~~

Dùng lệnh **javac** và **jar** giống nhau trên cả hai hệ điều hành. Với một JAR trên classpath, không cần dấu phân tách đường dẫn; nếu sau này có nhiều mục, phân tách bằng **:** trên Linux/macOS và **;** trên Windows.

### 3.3. Ba ca kiểm thử sử dụng cùng Client.java

**D01 — Có đúng thư viện: phải biên dịch được**

~~~text
javac --release 17 -classpath out/v1.jar -d out/dep-ok source/app/com/example/app/Client.java
~~~

**D02 — Thiếu thư viện: phải bị từ chối**

~~~text
javac --release 17 -classpath out/no-dep -d out/no-dep source/app/com/example/app/Client.java
~~~

**D03 — Sai chữ ký API: phải bị từ chối**

~~~text
javac --release 17 -classpath out/v2.jar -d out/type-conflict source/app/com/example/app/Client.java
~~~

| Ca | Exit status kỳ vọng | Nhóm chẩn đoán thường gặp | Ý nghĩa |
| --- | --- | --- | --- |
| D01 | 0 | Không có ERROR | Thư viện v1 đáp ứng API client dùng |
| D02 | Khác 0 | Package không tồn tại / cannot find symbol | Thiếu định nghĩa API tại compile time |
| D03 | Khác 0 | Incompatible types: int cannot be converted to String | Có API, nhưng chữ ký không tương thích |

**Lưu ý:** những mô tả lỗi trong bảng là diễn giải nội dung, không phải chuỗi nguyên văn bắt buộc trên mọi JDK/locale. Hãy kiểm tra exit code **ngay sau từng lần gọi javac**. Trên Bash/Zsh có thể dùng **echo $?**; trên PowerShell dùng **$LASTEXITCODE**. Thất bại biên dịch không tự động có nghĩa hạ tầng kiểm thử ổn: kiểm tra cả stderr/diagnostic và trạng thái tạo phụ thuộc.

### 3.4. Vì sao đây là “xung đột kiểu”, và chưa phải kiểm thử runtime?

Ca D03 giữ nguyên client rồi thay duy nhất API trong môi trường biên dịch. **javac** nhìn thấy chữ ký phương thức khác với kiểu client yêu cầu nên từ chối. Đó là một dạng *source incompatibility* có thể tái hiện trực tiếp.

Nếu client đã biên dịch với v1 rồi chạy với v2 mà không biên dịch lại, một lỗi liên kết tại runtime như **NoSuchMethodError** có thể xuất hiện. Đây là câu hỏi khác: *binary compatibility/linkage*. Không được coi việc client biên dịch thành công với v1 là bằng chứng nó sẽ chạy đúng với mọi phiên bản thay thế.

Tương tự, khi **hai JAR cùng chứa một lớp có fully qualified name giống nhau** trên classpath, **javac** không bắt buộc báo “duplicate class”; việc lớp nào được tìm thấy có thể phụ thuộc thứ tự đường dẫn và cách bố trí đầu vào. Không dùng một ca trùng FQCN như bằng chứng mặc định rằng trình biên dịch luôn phát hiện xung đột. Thay vào đó, ghim thứ tự/classpath, kiểm tra API thực sự được dùng, hoặc thiết kế ca cụ thể kiểm tra khả năng phân giải.

## 4. Xung đột tên kiểu: lỗi mơ hồ khác lỗi không tương thích API

Một xung đột kiểu khác xuất hiện khi có nhiều kiểu cùng **simple name** trong phạm vi import. Ví dụ cả **java.util** và **java.sql** đều có **Date**.

**NameConflict.java — phải bị từ chối:**

~~~java
import java.util.*;
import java.sql.*;

public class NameConflict {
    Date createdAt;
}
~~~

Với hai wildcard import, tham chiếu không đủ điều kiện **Date** bị mơ hồ. Đối chứng **NameResolved.java — phải biên dịch được:**

~~~java
public class NameResolved {
    java.util.Date createdAt;
}
~~~

Đối chứng đã chỉ định đầy đủ tên kiểu. Tạo thư mục đầu ra riêng, rồi chạy:

~~~text
javac --release 17 -d out/name-conflict NameConflict.java
javac --release 17 -d out/name-resolved NameResolved.java
~~~

Trước hai lệnh cần tạo **out/name-conflict** và **out/name-resolved**. Ca đầu kỳ vọng thất bại do **reference to Date is ambiguous**; ca sau thành công. Nếu lược bỏ import khiến Date không được tìm thấy thì đây lại là *missing symbol*, không phải *ambiguous type*; phải phân biệt theo nguyên nhân chẩn đoán.

## 5. JPMS: phân biệt tìm thấy module, đọc module và export package

Từ Java 9, mô-đun có thể đặt ranh giới biên dịch qua **module-info.java**. Cần tách bốn ý niệm:

1. **--module-path** chỉ nơi javac tìm các module đã biên dịch hoặc JAR mô-đun. Nó không thay thế classpath của code trên unnamed module.
2. **--module-source-path** chỉ cấu trúc nguồn nhiều named module để javac compile module từ source.
3. **requires com.example.library;** khai báo module hiện tại đọc module phụ thuộc; chỉ có module trên path chưa đủ để mọi named module tự động đọc nó.
4. **exports com.example.api;** cho phép module khác truy cập các kiểu **public** trong package được xuất. **requires** không vượt qua hàng rào **exports**. Một **public class** trong package không export vẫn không dùng trực tiếp được từ module khác.

Không đồng nhất **exports** với **opens**: **opens** chủ yếu cho deep reflection ở runtime và không tự tạo quyền truy cập API Java thông thường tại compile time. **exports ... to ...** còn có thể giới hạn danh sách module được truy cập. Các cơ chế **--add-reads**, **--add-exports**, **--patch-module** là tùy chọn đặc biệt có thể đổi hành vi kiểm thử; không bật ngầm chúng khi đang muốn xác minh ranh giới JPMS.

### 5.1. Bộ module chuẩn: phải biên dịch thành công

Tạo bốn file trong cây nguồn dưới đây:

~~~text
modules/ok/
  com.example.library/
    module-info.java
    com/example/api/Util.java
  com.example.consumer/
    module-info.java
    com/example/app/Main.java
~~~

**modules/ok/com.example.library/module-info.java**:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

**modules/ok/com.example.library/com/example/api/Util.java**:

~~~java
package com.example.api;

public final class Util {
    private Util() {}

    public static int answer() {
        return 42;
    }
}
~~~

**modules/ok/com.example.consumer/module-info.java**:

~~~java
module com.example.consumer {
    requires com.example.library;
}
~~~

**modules/ok/com.example.consumer/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.api.Util;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Util.answer());
    }
}
~~~

Tạo thư mục đầu ra và biên dịch cả hai named module từ source:

~~~text
javac --release 17 --module-source-path modules/ok -d mods/ok -m com.example.library,com.example.consumer
~~~

Điều kiện bắt buộc: **mods/ok** đã tồn tại trước khi gọi lệnh. **--module-source-path modules/ok** ở đây hoạt động vì các thư mục con được đặt theo tên module. Lệnh biên dịch phải thành công, tạo thư mục kết quả theo module bên dưới **mods/ok**. Chạy thử sau biên dịch (tùy chọn, chỉ để quan sát):

~~~text
java --module-path mods/ok -m com.example.consumer/com.example.app.Main
~~~

Stdout khi chạy:

~~~text
42
~~~

Đầu ra **42** là kiểm thử thực thi bổ sung; điều kiện PASS chính của ca kiểm thử biên dịch vẫn là javac thành công.

### 5.2. Ca M02 — Bỏ requires: phải bị từ chối

Sao chép nguyên bộ bốn tệp **modules/ok/** sang **modules/no-requires/**. Chỉ thay nội dung **modules/no-requires/com.example.consumer/module-info.java** bằng:

~~~java
module com.example.consumer {
}
~~~

Giữ nguyên module thư viện, class Util, class Main và lệnh compiler (chỉ đổi source root và output root):

~~~text
javac --release 17 --module-source-path modules/no-requires -d mods/no-requires -m com.example.library,com.example.consumer
~~~

Tạo **mods/no-requires** trước. Javac phải từ chối vì module **com.example.consumer** không đọc **com.example.library** dù package API có tồn tại và được export. Chẩn đoán thông dụng nêu package không visible do consumer không đọc module đó. Nếu sửa cả source Main hoặc bỏ module library cùng lúc, ta không còn một ca âm cô lập.

### 5.3. Ca M03 — Bỏ exports: phải bị từ chối

Sao chép bộ chuẩn sang **modules/no-exports/**. Giữ nguyên **requires** trong module consumer, nhưng thay riêng **modules/no-exports/com.example.library/module-info.java** bằng:

~~~java
module com.example.library {
}
~~~

Giữ nguyên class Util **public**. Chạy:

~~~text
javac --release 17 --module-source-path modules/no-exports -d mods/no-exports -m com.example.library,com.example.consumer
~~~

Sau khi tạo **mods/no-exports**, javac phải từ chối: consumer *đã đọc module library*, nhưng **com.example.api** không được export. Lỗi thường chứa ý “package ... is not visible” kèm lý do package không được export. Đây là nguyên nhân khác M02 dù phần đầu thông báo có thể giống nhau.

### 5.4. Ca thiếu module path khi biên dịch tách rời

Nếu module consumer được biên dịch **tách lượt** với module library, javac cần tìm được module library thông qua **--module-path**. Quy trình đối chứng:

1. Biên dịch **com.example.library** trước vào một thư mục đầu ra riêng.
2. Biên dịch **com.example.consumer** với **--module-path** trỏ đến thư mục chứa module library đã biên dịch: phải thành công.
3. Đổi riêng **--module-path** thành thư mục rỗng, giữ nguyên source consumer và **requires**: phải thất bại với chẩn đoán gần nghĩa “module not found: com.example.library”.

Không gộp ca này với M02: thiếu artifact module trên path và thiếu **requires** là hai lỗi cấu hình khác nhau. Trên Gradle/Maven, module path đôi khi được công cụ build tự suy luận; muốn kiểm tra quy tắc JPMS của **javac**, phải ghi lại lệnh/đường dẫn compiler thực nhận.

## 6. Bộ kiểm thử tự động gọi javac bằng Java 17+

Sau khi tạo các file fixture và JAR ở mục 3–5, có thể dùng một bộ chạy để không phải tự đọc exit code của từng lệnh. Chương trình dưới đây gọi chính javac của JDK hiện tại qua **ProcessBuilder**, tạo một thư mục đầu ra tạm riêng cho mỗi ca và in kết quả PASS. Vì sử dụng **ProcessBuilder(List<String>)**, nó không phải tự ghép câu lệnh shell hoặc lo escape dấu cách trong đường dẫn.

Lưu thành **CompileChecks.java** ở cùng thư mục cấp cao chứa **source/**, **modules/** và **out/**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CompileChecks {
    record Check(String name, boolean expectedSuccess, List<String> flags) {}

    static int invokeJavac(Path executable, Path workspace, List<String> flags)
            throws IOException, InterruptedException {
        List<String> command = new ArrayList<>();
        command.add(executable.toString());
        command.addAll(flags);

        Process process = new ProcessBuilder(command)
                .directory(workspace.toFile())
                .redirectErrorStream(true)
                .start();
        String log;
        try (var input = process.getInputStream()) {
            log = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            System.err.println("javac diagnostics (" + exitCode + "): " + log.strip());
        }
        return exitCode;
    }

    public static void main(String[] args) throws Exception {
        Path workspace = Path.of(".").toAbsolutePath().normalize();
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javac = Path.of(System.getProperty("java.home"), "bin",
                windows ? "javac.exe" : "javac");
        if (!Files.isRegularFile(javac)) {
            throw new IllegalStateException("Chạy bằng JDK có javac: " + javac);
        }

        Path root = Files.createTempDirectory("compilation-case-");
        List<Check> cases = List.of(
            new Check("dependency-present", true,
                List.of("--release", "17", "-cp", "out/v1.jar", "-d",
                    root.resolve("dep-ok").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("dependency-missing", false,
                List.of("--release", "17", "-cp", "out/no-dep", "-d",
                    root.resolve("dep-missing").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("api-signature-conflict", false,
                List.of("--release", "17", "-cp", "out/v2.jar", "-d",
                    root.resolve("api-conflict").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("modules-valid", true,
                List.of("--release", "17", "--module-source-path", "modules/ok",
                    "-d", root.resolve("module-ok").toString(),
                    "-m", "com.example.library,com.example.consumer")),
            new Check("modules-missing-requires", false,
                List.of("--release", "17", "--module-source-path",
                    "modules/no-requires", "-d",
                    root.resolve("module-no-requires").toString(),
                    "-m", "com.example.library,com.example.consumer")),
            new Check("modules-missing-exports", false,
                List.of("--release", "17", "--module-source-path",
                    "modules/no-exports", "-d",
                    root.resolve("module-no-exports").toString(),
                    "-m", "com.example.library,com.example.consumer"))
        );

        try {
            for (Check check : cases) {
                int index = check.flags().indexOf("-d");
                Files.createDirectories(Path.of(check.flags().get(index + 1)));
                int status = invokeJavac(javac, workspace, check.flags());
                if ((status == 0) != check.expectedSuccess()) {
                    throw new AssertionError(check.name() + " exited " + status);
                }
                System.out.println(check.name() + ": PASS");
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Chạy:

~~~text
javac -encoding UTF-8 CompileChecks.java
java CompileChecks
~~~

Stdout dự kiến (các diagnostic âm được in riêng ra stderr):

~~~text
dependency-present: PASS
dependency-missing: PASS
api-signature-conflict: PASS
modules-valid: PASS
modules-missing-requires: PASS
modules-missing-exports: PASS
~~~

Bộ chạy này đã được kiểm chứng bằng **javac JDK 21**: **6/6 ca PASS**; thêm cặp **NameConflict/NameResolved** ở mục 4 cũng đã được kiểm chứng độc lập. Lưu ý: mã nguồn của bộ chạy thực thi trên JDK 17+, nhưng bản thân compiler được gọi cần hỗ trợ **--release 17**.

**Phân tích giới hạn của harness:** phép so sánh **(status == 0) != expectedSuccess** kiểm tra sự chấp nhận/từ chối; nó **chưa tự chứng minh nguyên nhân chẩn đoán đúng**. stderr được in ra để người học đối chiếu. Trong hệ thống CI nghiêm ngặt hơn, cần đưa nguyên nhân kỳ vọng vào từng ca, ghi lại diagnostic và báo fail nếu nguyên nhân không khớp. Không coi “javac không chạy được”, timeout, file fixture thiếu, lỗi cấp quyền hoặc argument lỗi là một ca REJECT hợp lệ. Có thể phát triển harness dùng **javax.tools.JavaCompiler** với **DiagnosticCollector** để kiểm tra **Diagnostic.Kind.ERROR**, **getCode()**, **getSource()**, **getLineNumber()** và **getMessage(Locale)**; thông điệp/mã chi tiết có thể khác giữa phiên bản/triển khai compiler.

## 7. Thiết kế oracle và phòng tránh PASS giả

**Oracle** là tiêu chí quyết định PASS/FAIL. Một suite tốt có nhiều tầng xác minh:

| Tầng kiểm tra | Điều kiện tối thiểu | Mục đích |
| --- | --- | --- |
| Thiết lập | Tệp nguồn/JAR/module fixture đúng tên và tạo thành công | Không nhầm lỗi chuẩn bị dữ liệu |
| Ca dương | javac exit 0; nguồn cần kiểm tra thực sự được biên dịch | Khẳng định môi trường hợp lệ |
| Ca âm | javac exit khác 0 và có diagnostic biên dịch phù hợp | Khẳng định ràng buộc được thực thi |
| Đúng nguyên nhân | Thiếu package khác với sai kiểu; thiếu requires khác thiếu exports | Tránh negative pass giả |
| Cô lập | Output mới, classpath/module path được khai báo cụ thể | Tránh lớp hoặc dependency rác |
| Kiểm tra ngược | Đổi ca REJECT thành mã hợp lệ hoặc đổi kỳ vọng, suite phải fail | Kiểm tra tính hiệu lực của test harness |

Ví dụ, nếu ca D02 đáng lẽ thất bại vì không tìm thấy **VersionApi**, nhưng code client lại sai dấu ngoặc, chỉ kiểm tra **exit != 0** sẽ cho PASS giả. Hãy sửa client thành bản hợp lệ trước rồi thử lần lượt các cấu hình.

Để đánh giá diagnostic bền vững:

- **Loại lỗi:** trường hợp nguồn phải bị reject thường cần **Diagnostic.Kind.ERROR** nếu dùng JavaCompiler API.
- **Nguồn và ngữ cảnh:** kiểm tra tệp gây lỗi, loại quan hệ bị vi phạm và tên module/package/symbol liên quan khi phù hợp.
- **Mã thông báo:** diagnostic code đặc thù **javac** có thể hữu ích với bộ test ghim phiên bản nhưng không là hợp đồng bất biến của Java Language Specification.
- **Chuỗi thông báo:** không snapshot nguyên văn toàn bộ stderr làm điều kiện duy nhất vì locale, JDK, dòng/cột, đường dẫn tạm và thứ tự diagnostics có thể thay đổi.
- **Lỗi hạ tầng:** phân loại riêng khi không tạo được JVM process, thiếu JDK, phiên bản **--release** không hỗ trợ, JAR chưa build xong, không thể ghi thư mục, hoặc tiến trình chết bất thường.

Chỉ trả PASS cho negative case khi đã xác minh **lượt biên dịch thực sự diễn ra** và lỗi xuất phát từ điều kiện đã kiểm soát. Cặp đối chứng thay một tham số thường là bằng chứng mạnh nhất.

## 8. Classpath, module path và công cụ build: những bẫy hay gặp

### 8.1. Lẫn classpath và module path

Classpath phù hợp code thường trên **unnamed module**; named module có cơ chế đọc/xuất gói riêng. **--class-path** và **--module-path** không phải hai cách viết tương đương. JAR modular, automatic module và JAR thông thường có thể được xử lý khác nhau tùy cách đặt trên path. Khi test JPMS, ghi rõ mỗi thư viện được đưa vào path nào và module đang biên dịch thuộc loại gì.

### 8.2. Mở package bằng reflection nhưng quên exports

Thêm **opens** để framework reflection truy cập nội bộ không có nghĩa client khác được import trực tiếp kiểu ở package ấy. Với bài test truy cập API compile-time cần **exports**, và named consumer cần **requires**. Không được dùng chạy chương trình thành công do tùy chọn runtime như **--add-opens** làm bằng chứng biên dịch đã đáp ứng đúng ranh giới mô-đun.

### 8.3. Nhầm thiếu dependency compile-time với transitive dependency runtime

Mã có thể biên dịch được khi interface/class public hiện diện nhưng thất bại lúc chạy do một phụ thuộc triển khai hoặc liên kết động khác bị thiếu. Chiều ngược lại, nếu không có class cần dùng trên classpath của **javac**, lỗi là compile-time. Phải chỉ ra thời điểm lỗi: resolution ở build tool, javac, module resolution, class loading hay thực thi phương thức.

### 8.4. Dữ liệu build cũ và phụ thuộc ngoài ý muốn

Một lớp đã biên dịch sẵn trong **target/classes**, **build/classes**, thư mục IDE, hoặc JAR được tự động đưa vào classpath có thể che khuất một dependency bị thiếu. Cần compile trong output sạch, ghi rõ **-cp/--class-path** và **--module-path**, tránh dựa vào cấu hình IDE “đang chạy được”. Với Gradle/Maven, nên quan sát lệnh compiler thực tế và tập dependency được resolve, không chỉ tên dependency trong file build.

### 8.5. Annotation processing và generated sources

Nếu processor sinh lớp cần dùng, test “thiếu class” có thể pass/fail khác nhau tùy processor path, tùy chọn **-proc** và generated source. Với bài kiểm thử quy tắc Java cơ bản, tắt processor khi cần cô lập; với bài kiểm thử processor, hãy khai báo processor path và kiểm tra output sinh ra như một điều kiện riêng. Tránh vô tình đưa generated source cũ vào lượt compile.

### 8.6. Cấu hình --release và JDK thực chạy

**--release 17** xác định mức source/API chuẩn Java 17, không bảo đảm dùng đúng mọi phiên bản thư viện bên thứ ba. Khi lỗi đến từ chênh lệch phiên bản JAR, cần ghim artifact thực tế và ghi lại SHA-256 hoặc phiên bản đã dùng. Đừng kết luận “Java 17 không hỗ trợ API” khi nguyên nhân là phụ thuộc chưa có trong classpath.

## 9. Tích hợp vào CI và mở rộng bài thực hành

Trong dự án thật, có thể lưu fixture sai có chủ đích ở **src/test/resources/compile-fixtures/** (hoặc cây dữ liệu tương đương) thay vì đưa trực tiếp vào source set Java mặc định. Task/harness sẽ chuẩn bị thư viện, compile từng fixture và thu thập kết quả. Không để file Java cố ý sai bị Gradle/Maven biên dịch cùng test runner trước khi test có cơ hội chạy.

Đề xuất metadata cho một ca có thể lưu dưới YAML/JSON hoặc cấu trúc test code:

~~~yaml
id: M03
title: Named module does not export API package
jdkRelease: 17
sourceRoot: modules/no-exports
expected: REJECT
expectedReason: com.example.api is not exported by com.example.library
compilerOptions:
  - --release
  - "17"
  - --module-source-path
  - modules/no-exports
~~~

Manifest chỉ mô tả dữ liệu; phải có runner thực sự tạo output sạch, gọi compiler, đọc diagnostics và đối chiếu nguyên nhân. Khi cập nhật JDK hoặc thư viện, hãy chạy lại cả cặp đối chứng trước khi thay đổi kỳ vọng.

**Bài thực hành A — thiếu module path:** tách quá trình build thư viện và consumer ở mục 5 thành hai lượt. Cho consumer đọc thư viện bằng **--module-path** đúng rồi cố ý thay bằng một thư mục rỗng. Ghi lại chẩn đoán **module not found**, phân biệt với ca bỏ **requires**.

**Bài thực hành B — thay đổi overload:** tạo API v1 có phương thức **parse(String)** và consumer gọi **parse("42")**. Tạo API v2 chỉ có **parse(int)**, giữ client nguyên. Kiểm tra cặp ACCEPT/REJECT theo cùng classpath test D01–D03, rồi giải thích vì sao thông báo khác trường hợp thay kiểu trả về.

**Bài thực hành C — kiểm tra harness:** sửa file **VersionApi v2** sao cho **version()** trả **String** giống v1, build lại JAR v2. Ca “api-signature-conflict” trong harness **phải báo FAIL** vì mã nay hợp lệ. Khôi phục API v2, đảo kỳ vọng ca “modules-missing-exports” thành ACCEPT; harness cũng phải báo FAIL. Đây là bằng chứng bộ test thực sự phát hiện thay đổi quy tắc.

Tiêu chí hoàn thành:

1. Có ít nhất một cặp positive/negative cho thiếu classpath dependency, xung đột kiểu và JPMS.
2. Mỗi cặp chỉ thay đổi một điều kiện liên quan, những file khác giữ nguyên.
3. Mọi ca positive được javac chấp nhận; mọi ca negative bị từ chối vì nguyên nhân dự kiến.
4. Không đánh đồng lỗi Javac, lỗi hạ tầng, lỗi của build tool, lỗi runtime và lỗi JPMS với nhau.
5. Bộ test dùng output sạch, khai báo JDK/release/path, ghi diagnostic để debug và thất bại khi cố tình phá hỏng một kỳ vọng.

**Kết luận chuyên môn:** kiểm thử compilation configuration cần chứng minh cùng mã nguồn vượt qua hoặc bị chặn bởi *ranh giới phụ thuộc, kiểu và khả năng truy cập module* cụ thể. Một exit code thất bại chỉ là tín hiệu; giá trị học tập nằm ở việc lý giải **tại sao compiler từ chối** và kiểm chứng rằng một cấu hình đối chứng hợp lệ vẫn được chấp nhận.