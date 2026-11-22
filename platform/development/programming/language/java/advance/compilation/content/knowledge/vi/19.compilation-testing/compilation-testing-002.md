# Kiểm tra trạng thái lỗi thay vì chỉ so chuỗi thông báo khi kiểm thử biên dịch Java

## 1. Vấn đề: thông báo lỗi không phải hợp đồng ổn định của compiler

Giả sử một bài kiểm thử tạo đoạn Java sai kiểu dữ liệu và mong đợi trình biên dịch từ chối mã nguồn. Cách kiểm thử dễ viết nhưng dễ vỡ là khẳng định thông báo in ra phải chứa chính xác câu tiếng Anh như `incompatible types: String cannot be converted to int`.

Mục tiêu thực sự của bài kiểm thử đó không phải “compiler đã in đúng câu tiếng Anh”, mà là **mã nguồn không biên dịch được do có lỗi**. Câu chữ là cách công cụ *trình bày* kết quả; còn trạng thái và diagnostic là bằng chứng cho *hành vi* biên dịch.

Đây là khác biệt cốt lõi:

- **Trạng thái biên dịch:** thành công hay thất bại (`JavaCompiler.CompilationTask.call()`, exit code của `javac`, trạng thái task build).
- **Diagnostic có cấu trúc:** mức độ (`ERROR`, `WARNING`…), vị trí source, mã diagnostic nếu compiler cung cấp và thông điệp giải thích.
- **Thông báo hiển thị:** văn bản đã được formatter, locale và implementation tạo ra cho con người đọc. Phần này có thể thay đổi dù hành vi compiler vẫn đúng.

Một test tốt nên nói rõ **điều kiện bất biến muốn bảo đảm**, rồi kiểm tra ở mức phù hợp. Đối với trường hợp mã Java phải bị từ chối, điều kiện chính là task biên dịch thất bại, thường kèm diagnostic loại `ERROR` cho lỗi nguồn đã chuẩn bị.

## 2. Vì sao so khớp toàn bộ message dễ gây false failure?

Thông báo lỗi phụ thuộc nhiều biến:

| Nguồn thay đổi | Ví dụ ảnh hưởng | Kết quả đối với so khớp nguyên chuỗi |
|---|---|---|
| Phiên bản JDK/`javac` | Câu giải thích, vị trí gợi ý, định dạng diagnostic thay đổi | Test đỏ dù mã vẫn bị từ chối đúng |
| Locale/ngôn ngữ | Message được localize hoặc xử lý bởi wrapper | Test tiếng Anh không còn khớp |
| Cờ compiler | `-Xlint`, `-Werror`, `-XDrawDiagnostics` thay đổi loại/định dạng kết quả | Snapshot văn bản dễ lệch |
| File path và môi trường | Đường dẫn tuyệt đối/tương đối, dấu phân cách trên OS, working directory | So khớp toàn bộ stderr không ổn định |
| Thứ tự và số lượng diagnostic | Một lỗi cú pháp có thể dẫn đến diagnostic tiếp theo | Test phụ thuộc số dòng dễ vỡ |
| Compiler/tooling khác | ECJ, `javac`, wrapper IDE/build tool có cách diễn đạt khác nhau | Test bị khóa vào formatter |
| Annotation processor/plugin | Có thể báo lỗi riêng, thêm tiền tố hoặc vị trí | Message thay đổi ngoài ý muốn của lesson |

Chẳng hạn cùng một lỗi không gán được `String` cho `int`, hai compiler hoặc hai phiên bản có thể cung cấp thông báo khác nhau. Việc so khớp `stderr.contains("incompatible types")` vẫn dễ hỏng nếu text được dịch hoặc diễn đạt lại.

Tuy nhiên, không vì thế mà **mọi** kiểm tra message đều sai. Nếu mục tiêu của sản phẩm là **giao diện thông báo cho người dùng** (ví dụ một wrapper compiler phải in tên file hoặc một mã lỗi do chính dự án định nghĩa), có thể kiểm tra phần thông báo thuộc hợp đồng sản phẩm, với môi trường được cố định và test phù hợp. Hãy tách các kiểm thử giao diện này khỏi test về tính hợp lệ ngôn ngữ Java.

## 3. Các mức kiểm tra, từ ổn định đến đặc thù

Chọn assertions theo thứ tự dựa trên mục tiêu kiểm thử:

1. **Kết quả compile:** lệnh hay tác vụ kết thúc thành công/thất bại đúng dự kiến.
2. **Mức độ diagnostic:** có ít nhất một `Diagnostic.Kind.ERROR` với test nguồn sai; hoặc không có `ERROR` với nguồn hợp lệ.
3. **Nguồn và vị trí khi cần:** lỗi liên quan tới unit đang thử, số dòng/cột thuộc phạm vi mong đợi; không bắt buộc vị trí nếu đặc tả không hứa.
4. **Mã diagnostic** (`Diagnostic.getCode()`) chỉ khi công cụ/phiên bản cung cấp và hợp đồng test đủ hẹp. Theo Java API, mã là **implementation-dependent** và có thể `null`; không phải định danh lỗi chuẩn hóa xuyên mọi compiler.
5. **Thông điệp văn bản** khi nội dung chữ thật sự là yêu cầu cần kiểm chứng, ưu tiên đoạn do **chính ứng dụng** sở hữu hoặc một snapshot được bảo vệ bằng kiểm soát phiên bản, locale, OS và compiler.

Không nên mặc định assert `getDiagnostics().size() == 1`. Một lỗi chính có thể tạo nhiều diagnostic theo phiên bản hoặc cờ biên dịch. Nếu điều cần chứng minh là có lỗi, `anyMatch(kind == ERROR)` diễn đạt đúng hơn việc đếm cứng toàn bộ thông báo.

**Điểm quan trọng:** `Diagnostic.Kind.ERROR` mô tả loại chẩn đoán. Kết quả tổng thể vẫn phải được kiểm tra độc lập: ví dụ cấu hình “warnings as errors” có thể làm compiler thất bại theo chính sách cảnh báo, ngay cả khi các diagnostic nổi bật là warning. Vì vậy, test negative compile chỉ dựa vào “có ERROR” có thể bỏ sót một con đường thất bại khác; ngược lại chỉ dựa vào `call() == false` không chứng minh chính xác lý do thất bại là gì.

## 4. Java 17+: ví dụ test biên dịch lỗi bằng API có cấu trúc

Java cung cấp Java Compiler API trong module chuẩn `java.compiler`, package `javax.tools`. `JavaCompiler` cho phép biên dịch từ chương trình Java, còn `DiagnosticCollector` thu nhận diagnostic mà không phải phân tích output của terminal.

Dưới đây là **một chương trình Java đầy đủ, chạy độc lập bằng JDK 17+**. Chương trình tạo một tệp nguồn trong bộ nhớ với phép gán sai kiểu và khẳng định compiler phải từ chối nguồn đó.

**Tệp: `CompilerDiagnosticsTest.java`**

```java
import java.net.URI;
import java.util.List;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CompilerDiagnosticsTest {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK compiler is required");
        }

        String invalidSource =
                "class Broken { int number = \"text\"; }";

        JavaFileObject sourceFile =
                new InMemorySource("Broken", invalidSource);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Boolean success = compiler.getTask(
                null,                    // output writer: default
                null,                    // file manager: standard
                diagnostics,             // structured diagnostics
                List.of("-proc:none"),   // no annotation processors
                null,                    // classes: none
                List.of(sourceFile)       // compilation units
        ).call();

        boolean compilationFailed = Boolean.FALSE.equals(success);
        boolean hasErrorDiagnostic = diagnostics.getDiagnostics()
                .stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        if (!compilationFailed || !hasErrorDiagnostic) {
            throw new AssertionError(
                    "Expected compilation failure with ERROR diagnostic");
        }

        System.out.println("Compilation failed: " + compilationFailed);
        System.out.println("ERROR diagnostic found: " + hasErrorDiagnostic);
    }

    private static final class InMemorySource extends SimpleJavaFileObject {
        private final String source;

        private InMemorySource(String className, String source) {
            super(
                    URI.create("string:///" + className
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE
            );
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }
}
```

Chạy tại thư mục chứa tệp:

```bash
javac CompilerDiagnosticsTest.java
java CompilerDiagnosticsTest
```

Kết quả stdout mong đợi:

```text
Compilation failed: true
ERROR diagnostic found: true
```

Ví dụ dùng đoạn nguồn **không hợp lệ có chủ ý**, nên lời gọi biên dịch bên trong chương trình trả về `false`. Nhưng *chính chương trình test* được biên dịch và chạy thành công; nếu assertion sai, chương trình test ném `AssertionError`. Vì source lỗi được tạo trong bộ nhớ và compilation thất bại, không có `Broken.class` hợp lệ cần chạy.

Giải thích các phần quan trọng:

- `ToolProvider.getSystemJavaCompiler()`: tìm compiler của môi trường hiện tại. Có thể trả `null` nếu runtime không cung cấp system compiler; chạy ví dụ bằng **JDK**, không chỉ một runtime tối giản.
- `SimpleJavaFileObject`: bọc chuỗi source thành một compilation unit với URI và loại `SOURCE`.
- `DiagnosticCollector<JavaFileObject>`: nhận các bản ghi diagnostic riêng biệt, thay vì parse lỗi in ra console.
- `compiler.getTask(...).call()`: chạy compilation task; kết quả `Boolean` biểu diễn thành công hay thất bại.
- `List.of("-proc:none")`: vô hiệu hóa annotation processing để fixture chỉ kiểm tra lỗi gán kiểu, giảm tác động của processor bên ngoài.
- `anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR)`: xác nhận ít nhất một lỗi của compiler; không phụ thuộc câu tiếng Anh hoặc số lượng lỗi phụ.

Ta không cần assert message `incompatible types`, `cannot be converted` hay vị trí chính xác của dấu ngoặc để chứng minh hành vi mong đợi.

### 4.1. Vì sao đây là test đáng tin hơn so chuỗi?

Xét assertion không bền:

```java
// Minh họa anti-pattern; không phải chương trình độc lập.
assertTrue(stderr.contains(
        "incompatible types: java.lang.String cannot be converted to int"));
```

Nó trộn lẫn hai hợp đồng khác nhau: “source sai kiểu bị từ chối” và “compiler diễn đạt lỗi bằng một câu cụ thể”. Test API ở trên chỉ khẳng định hợp đồng thứ nhất; một bản cập nhật JDK thay đổi lời văn nhưng vẫn từ chối mã sai sẽ không làm test hỏng.

### 4.2. Khi cần xác nhận vị trí lỗi

`javax.tools.Diagnostic` còn hỗ trợ:

```java
// Fragment minh họa để đặt sau khi đã thu được diagnostics.
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        long line = d.getLineNumber();
        long column = d.getColumnNumber();
        JavaFileObject source = d.getSource();
        String code = d.getCode();

        // Chỉ assert vị trí khi hành vi/compiler yêu cầu;
        // xử lý Diagnostic.NOPOS và source/code có thể null.
    }
}
```

Vị trí dòng/cột là metadata hỗ trợ test và debugging. API có `Diagnostic.NOPOS` khi không có vị trí phù hợp. `getSource()` cũng có thể `null`. Một assertion `line == 1` sẽ kém ổn định nếu fixture thêm dòng trống hoặc trình biên dịch quy lỗi sang token khác; khi đặc tả chỉ cần báo lỗi đúng file, kiểm tra URI của source hoặc phạm vi vị trí có ý nghĩa sẽ hợp lý hơn.

## 5. Kiểm thử bằng CLI: exit code quan trọng hơn stderr

Không phải test nào cũng dùng Compiler API. Trong script CI hoặc integration test, `javac` thường chạy như một tiến trình con:

```text
Test fixture Java source
          |
          v
    javac subprocess
          |
          +-- exit code ----> assertion chính
          |
          +-- stdout/stderr -> log để chẩn đoán
```

Ví dụ, tạo **`BadExample.java`**:

```java
class BadExample {
    int age = "not a number";
}
```

Trên shell POSIX (bash/zsh), có thể xác minh kết quả mà không so chuỗi:

```bash
if javac BadExample.java; then
    echo "Unexpected success"
    exit 1
else
    echo "Compilation failed as expected"
fi
```

Khi dùng compiler JDK bình thường, kết quả của script là:

```text
Compilation failed as expected
```

Lưu ý: `javac` vẫn có thể in diagnostic ra stderr ngoài dòng echo trên. Dòng thể hiện ở đây là **stdout do script tạo**, không tuyên bố toàn bộ output terminal chỉ có một dòng.

Với **PowerShell** có thể kiểm tra `$LASTEXITCODE` ngay sau khi chạy ứng dụng native `javac`:

```powershell
javac BadExample.java
if ($LASTEXITCODE -eq 0) {
    throw "Unexpected compilation success"
}
Write-Output "Compilation failed as expected"
```

Dòng `$LASTEXITCODE` biểu thị exit code của tiến trình native gần nhất; kiểm tra ngay sau `javac` để không bị lệnh khác thay thế. Script dùng negative fixture có lỗi chắc chắn, nhưng **non-zero exit code một mình không đủ chứng minh đó là lỗi loại mong đợi**: ví dụ `javac` không được tìm thấy, file không tồn tại, quyền truy cập bị từ chối hoặc invocation không hợp lệ cũng có thể làm test thất bại. Vì vậy, trong integration test nên kiểm tra cả việc tiến trình khởi chạy đúng, source fixture tồn tại và các tín hiệu diagnostic phù hợp.

### 5.1. Không lẫn compile status với số lỗi in ra

`javac` CLI cung cấp exit code, nhưng mặc định không cung cấp một JSON diagnostic chuẩn hóa. Nếu bạn chỉ có stdout/stderr, hãy:

1. Assert exit code theo mục tiêu positive/negative.
2. Giữ stderr làm dữ liệu **troubleshooting** khi test thất bại.
3. Nếu bắt buộc xác nhận **loại lỗi**, cân nhắc dùng Java Compiler API hoặc một adapter được dự án định nghĩa có schema ổn định.
4. Nếu dùng compiler-specific option như `-XDrawDiagnostics` để hỗ trợ phân tích, nhớ rằng mã và format được **gắn với implementation**, không được Java SE cam kết ổn định giữa các vendor/version.

Đừng dùng `stderr.isBlank()` làm điều kiện duy nhất để suy ra compilation thành công: một tool có thể in cảnh báo lên stderr mà vẫn trả mã 0; ngược lại tool có thể thất bại do lỗi cấu hình trước khi sinh diagnostic nguồn.

## 6. Thiết kế bộ test với kết quả positive, negative và warning

Một bộ test compilation nên diễn đạt từng hợp đồng độc lập:

| Trường hợp | Điều nên kiểm tra | Điều không nên mặc định |
|---|---|---|
| Source Java hợp lệ | Compilation thành công; không có diagnostic `ERROR` | Không có bất kỳ message nào |
| Source sai kiểu dữ liệu | Compilation thất bại; có `ERROR` | Câu text cụ thể và đúng một lỗi |
| Source thiếu symbol | Compilation thất bại; diagnostic phù hợp với fixture | Dòng message `cannot find symbol` phải giữ nguyên |
| Có warning nhưng policy cho phép | Compilation thành công; cảnh báo được thu nhận nếu test cần | Warning luôn ở stderr hoặc luôn có đúng một bản ghi |
| Bật `-Werror` | Compilation có thể thất bại do warnings được xem là lỗi | Mọi diagnostic đều đổi loại thành `ERROR` |
| Processor chủ động báo lỗi | Compilation thất bại và có diagnostic phù hợp | Source line hoặc message giống lỗi của `javac` thuần |
| Tool không khởi chạy được | Test thất bại do hạ tầng/configuration | Được tính là bài kiểm thử “source bị từ chối” thành công |

**Negative test phải loại bỏ khả năng false positive vì hạ tầng.** Nếu chạy một tiến trình `javac`, ghi rõ executable, working directory, classpath/module-path, JDK version và source units thực tế. Một exit code khác 0 không xác nhận việc compiler đã đọc đúng fixture.

**Positive test phải xác nhận đúng điều kiện thành công.** Khi có warning, đừng yêu cầu “không có diagnostic” nếu mục tiêu chỉ là chấp nhận nguồn hợp lệ. Khi policy bắt buộc sạch warning, đó là một hợp đồng riêng cần thiết lập flags và assertion rõ ràng.

## 7. Dùng JUnit 5: tách assertion khỏi dữ liệu thông báo

Trong dự án có JUnit Jupiter, có thể chuyển logic của ví dụ Compiler API thành helper trả về kết quả:

```java
// Các đoạn sau là minh họa API test, không phải lớp độc lập.
record CompileResult(
        boolean succeeded,
        List<Diagnostic<? extends JavaFileObject>> diagnostics) {

    boolean containsError() {
        return diagnostics.stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
    }
}
```

Khi helper `compile(source)` đã được cài đặt bằng Java Compiler API và trả về `CompileResult`, những assertion theo hợp đồng có thể viết:

```java
// Fragment JUnit 5, yêu cầu helper compile(...) và imports phù hợp.
@Test
void invalidAssignmentMustBeRejected() {
    CompileResult result = compile(
            "class Bad { int count = \"oops\"; }");

    assertFalse(result.succeeded());
    assertTrue(result.containsError());
}

@Test
void validAssignmentMustCompile() {
    CompileResult result = compile(
            "class Good { int count = 7; }");

    assertTrue(result.succeeded());
    assertFalse(result.containsError());
}
```

Hai fragment được ghi rõ là **minh họa phụ thuộc helper**; chương trình chạy độc lập ở mục 4 là ví dụ đầy đủ không yêu cầu JUnit.

Có thể thêm assertion thông tin diagnostic để giúp đọc khi test lỗi, chẳng hạn dùng `assertAll(...)` và message lambda chứa danh sách diagnostic. Cần phân biệt **thông báo đi kèm assertion thất bại** (hữu ích để chẩn đoán) với **chuỗi được assert là nội dung mong đợi** (dễ làm test giòn).

Nếu chính sách build đòi hỏi diagnostic thuộc đúng một file nguồn, hãy kiểm tra `getSource()` trước khi so URI; nếu bài tập chỉ cần chứng minh mã không compile, việc kiểm tra source/line/column chi tiết sẽ thêm rủi ro mà không tăng độ tin cậy.

## 8. Assertion cho compiler diagnostic code: khi nào có giá trị?

API `Diagnostic.getCode()` trả một mã loại diagnostic, nhưng tài liệu Java SE cho biết mã **phụ thuộc implementation và có thể null**. Các mã được `javac` cung cấp trong một số ngữ cảnh có thể rất hữu ích cho việc phân tích regression khi đội ngũ **khóa đúng JDK và compiler**.

Phân loại hợp đồng:

- **Hợp đồng Java language / compiler integration:** compile pass/fail, `Kind.ERROR`, nguồn và vị trí ở mức cần thiết. Không khóa toàn bộ message.
- **Hợp đồng của một javac version cố định:** có thể kiểm tra mã diagnostic đặc thù nếu đội kiểm thử sở hữu baseline/version và có kế hoạch cập nhật khi nâng JDK.
- **Hợp đồng của sản phẩm xây trên compiler:** nên chuyển diagnostic từ compiler thành **mã lỗi nội bộ ổn định** của sản phẩm trước khi public API hoặc test dựa vào nó.

Ví dụ một hệ thống học tập có thể ánh xạ diagnostic đã phân loại sang `JAVA_TYPE_MISMATCH` trong domain của mình. Khi đó test API nội bộ có thể assert `JAVA_TYPE_MISMATCH` dù câu tiếng Anh do `javac` tạo ra thay đổi. Tuy nhiên, **ánh xạ đó là mã do ứng dụng tự xây**, không phải Java Compiler API mặc định đã cung cấp danh sách mã domain chuẩn hóa như vậy.

Nếu sản phẩm chưa có lý do kiểm tra từng phân loại lỗi, hãy giữ test đơn giản và kiểm tra `ERROR` cùng trạng thái compile.

## 9. Các điểm đặc biệt: warning, lỗi tool, và annotation processor

### 9.1. Warning không đồng nhất với lỗi

`Diagnostic.Kind` có các giá trị `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. Không phải mọi diagnostic xuất hiện đều làm compilation thất bại. Cờ `-Xlint` có thể bật cảnh báo; `-Werror` yêu cầu fail khi warning xuất hiện trong `javac`.

Đối với fixture có chủ đích gây warning, hai cách kiểm thử là:

- Khi policy cho phép warning: khẳng định compilation success, rồi kiểm tra một warning *nếu* bài test chủ đích xác minh warning ấy.
- Khi policy cấm warning: bật `-Werror`, kiểm tra compilation failure và xác minh cơ chế cảnh báo phù hợp. Không giả định mọi warning biến thành `Kind.ERROR`.

Một bài kiểm thử chỉ dùng `hasErrorDiagnostic` làm cờ “compile failed” sẽ không bao quát đầy đủ policy warnings-as-errors. Hãy đánh giá cả **kết quả task** lẫn **loại diagnostic** theo từng mục tiêu.

### 9.2. Lỗi invocation và lỗi compilation phải khác nhau

Trong Java Compiler API, `ToolProvider.getSystemJavaCompiler()` có thể trả về `null` ở môi trường không có compiler. Gọi API sai, dùng tùy chọn không hợp lệ hoặc lỗi I/O cũng có thể dẫn đến ngoại lệ hay failure khác với việc Java source sai kiểu.

Một bộ test đáng tin nên coi lỗi hệ thống build là **test infrastructure failure**; không “pass” test nguồn sai chỉ vì mọi thứ thất bại. Với process test, kiểm tra compiler executable tồn tại và khởi chạy; với API test, xác nhận compiler khác `null` và kiểm soát exception riêng biệt.

### 9.3. Annotation processor tạo diagnostic của riêng nó

Processor có thể dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` để chặn build khi annotation không hợp lệ. Đây là thông báo từ processor, không nhất thiết có cùng câu chữ, vị trí hay mã của lỗi type checking của `javac`.

Nếu mục tiêu test là processor:

- Cung cấp annotation/input nhỏ, cố định.
- Kiểm tra compilation failure và diagnostic `ERROR` từ invocation dùng processor.
- Xác minh source/element hoặc **mã domain do processor sở hữu** nếu có một contract như vậy.
- Kiểm tra các trường hợp được chấp nhận không phát sinh lỗi và sinh artifact đúng.
- Không bật `-proc:none` trong test processor; cờ đó chỉ dùng ở ví dụ mục 4 để loại processor khỏi phạm vi kiểm thử.

## 10. Kết hợp với Gradle và Maven mà không nhầm tầng

Với Gradle hay Maven, test compile có thể diễn ra ở nhiều tầng:

```text
Java source (có thể sai cố ý)
         |
         v
javac / compiler provider
  |          |
  |          +-- structured diagnostics / stdout / stderr
  v
compiler success/failure
         |
         v
Gradle task hoặc Maven plugin goal
         |
         v
build success/failure + test report
```

Không phải trạng thái của task build là một `Diagnostic.Kind`. Ví dụ `:compileJava` thất bại còn có thể do dependency resolution, thiếu toolchain, annotation processor exception hoặc lỗi cấu hình, chứ không chỉ vì cú pháp Java. Tương tự, một build đã `UP-TO-DATE` không nhất thiết đã chạy lại negative fixture trong lượt đó.

Để kiểm tra một fixture cố tình sai mà vẫn giữ build chính chạy ổn định, hãy đặt nó thành **đầu vào test riêng** được gửi đến Compiler API hoặc compiler invocation trong test harness, **không** đưa nó vào source set sản phẩm `src/main/java` khiến mọi build đều fail.

Nếu dùng Gradle Test task hoặc Maven Surefire để chạy JUnit tích hợp compiler, cần đảm bảo test không bị vô tình bỏ qua do task up-to-date/cache khi đang xác minh fixture mới. Chỉ sử dụng cơ chế ép rerun khi thật sự cần chẩn đoán. Cấu hình compiler và classpath cho test fixture phải được kiểm soát rõ, nhất là với project nhiều module.

## 11. Mẫu anti-pattern và cách sửa

| Anti-pattern | Vì sao kém tin cậy | Cách thay thế |
|---|---|---|
| `assertEquals("...full compiler error...", stderr)` | Phụ thuộc formatter, locale, đường dẫn, version | Assert fail status + diagnostic `ERROR` |
| `assertTrue(stderr.contains("cannot find symbol"))` | Câu chữ implementation-dependent | Assert lỗi từ source fixture với compiler API |
| `assertEquals(1, diagnostics.size())` | Diagnostic có thể thêm warning/note hoặc nhiều lỗi | `anyMatch(kind == ERROR)` hoặc lọc chính xác theo nhu cầu |
| `assertFalse(success)` mà không kiểm tra nguyên nhân | Tool hỏng cũng có thể báo failure | Xác minh compiler khởi chạy, fixture đúng, diagnostic phù hợp |
| `assertNotNull(d.getCode())` cho mọi compiler | `getCode()` có thể null theo API | Chỉ kiểm tra mã khi compiler contract bảo đảm |
| Assert chính xác line/column ở mọi test | Thay đổi formatting/diagnostic span gây vỡ | Chỉ kiểm tra vị trí khi là yêu cầu |
| Coi `WARNING` là `ERROR` | Làm sai phân loại và chính sách `-Werror` | Kiểm tra `Kind` và task result độc lập |
| Đưa nguồn intentionally invalid vào main source set | Làm cả project fail trước khi test chạy | Dùng in-memory fixture hoặc thư mục test riêng |
| Bắt mọi exception rồi coi là “expected compile failure” | Che lỗi hạ tầng/compiler invocation | Phân biệt exception hạ tầng và diagnostic nguồn |

### Khi nào snapshot thông báo là lựa chọn hợp lý?

Snapshot hữu ích nếu bạn đang kiểm thử **UX của một trình biên tập, linter hoặc CLI do dự án sở hữu**, nơi format thông báo là chức năng có người dùng phụ thuộc. Khi đó nên:

1. Cố định JDK, compiler, locale, timezone và đường dẫn tương đối của fixture phù hợp.
2. Phân lớp: unit test ngữ nghĩa compile dùng status/diagnostic; snapshot test chỉ kiểm tra lớp formatter.
3. Chuẩn hóa các chi tiết không thuộc hợp đồng (temporary directory, path separator, màu ANSI) trước khi so snapshot.
4. Duyệt thay đổi snapshot khi nâng toolchain, không cập nhật golden file một cách mù quáng.

Với test mục tiêu “Java source này phải bị từ chối”, snapshot message thường là chi phí bảo trì không cần thiết.

## 12. Quy trình thiết kế một test compilation đáng tin

**Bước 1 — Viết yêu cầu bằng ngôn ngữ hành vi.** “Mã gán chuỗi cho biến int phải bị từ chối” hoặc “đoạn khai báo hợp lệ phải compile thành công”. Tránh đưa câu text của compiler vào yêu cầu ngay từ đầu.

**Bước 2 — Chọn tầng test.** Kiểm tra ngữ nghĩa Java ngay trong JVM bằng `JavaCompiler`, CLI bằng `javac`, hay kết quả end-to-end qua Gradle/Maven. Tầng càng cao càng cần phân biệt lỗi toolchain/dependency với lỗi source.

**Bước 3 — Chuẩn bị fixture tối thiểu.** Dùng một compilation unit nhỏ, tên file/class phù hợp, không đòi thư viện ngoài nếu test không chủ đích kiểm tra classpath. Tránh một source có nhiều lỗi độc lập vì compiler có thể phát sinh diagnostic phụ thuộc thứ tự.

**Bước 4 — Kiểm tra primary outcome.** Assert `call() == false` hoặc compiler process trả non-zero với test negative; ngược lại assert success với test positive.

**Bước 5 — Bổ sung tín hiệu kiểm chứng nguyên nhân.** Với negative type error, kiểm tra có `Kind.ERROR` và compiler nhận đúng source. Với test annotation processor, có thể dùng thêm marker hoặc mã do processor sở hữu.

**Bước 6 — Đưa văn bản vào thông tin debug.** Khi assertion fail, log các diagnostic cùng `kind`, `source`, `line`, `column`, `code`, `message` để người bảo trì đọc, nhưng đừng so nguyên văn những trường không thuộc hợp đồng.

**Bước 7 — Thử nâng compiler/đổi locale (khi thực tế cần).** Một test tốt về ngữ nghĩa phải còn giá trị khi lời văn diagnostic thay đổi; nếu không, quay lại xem assertion đã ràng buộc nhầm phần formatter hay chưa.

## 13. Bài tập kiểm tra hiểu biết

**Bài 1.** Test cho đoạn `int quantity = "3";` hiện assert `stderr.contains("incompatible types")`. Trên một JDK khác, text đổi nhưng compilation vẫn fail. Test có nên fail không?

*Đáp án gợi ý:* Nếu mục tiêu kiểm tra tính hợp lệ Java, không. Sửa để kiểm tra compile failure và `Diagnostic.Kind.ERROR`, đồng thời bảo đảm fixture được đưa tới compiler đúng cách.

**Bài 2.** Chạy `javac` trả mã khác 0 vì thiếu tệp source. Đây có phải negative compilation test pass?

*Đáp án gợi ý:* Không. Đây là lỗi setup/invocation; source chưa được đánh giá theo quy tắc ngôn ngữ. Phải xác minh fixture tồn tại và kiểm tra diagnostic của trường hợp cần thử.

**Bài 3.** Có diagnostic loại `WARNING` và compiler trả success. Bạn nên kiểm tra điều gì?

*Đáp án gợi ý:* Xem policy của bài test. Nếu warning được phép, kết quả là thành công; nếu bài test bảo đảm không có warning, kiểm tra warning trực tiếp hoặc cấu hình `-Werror`. Không tự đổi loại warning thành error.

**Bài 4.** Một plugin do đội phát triển viết có mã `VALIDATION_DUPLICATE_NAME` độc lập với JDK. Có nên assert mã đó không?

*Đáp án gợi ý:* Có, nếu đó là hợp đồng ổn định của plugin. Hãy phân biệt mã domain do dự án sở hữu với `Diagnostic.getCode()` mang tính implementation-dependent của compiler.

**Bài 5.** Một test assert `getLineNumber() == 1`, sau khi thêm dòng comment đầu file thì test đỏ dù lỗi vẫn phát hiện đúng. Sửa thế nào?

*Đáp án gợi ý:* Nếu vị trí chính xác không thuộc mục tiêu, bỏ assertion hoặc thay bằng kiểm tra lỗi nằm trong đúng source. Nếu vị trí là hành vi cần test, cập nhật fixture và kỳ vọng có chủ đích, xét `Diagnostic.NOPOS`.

## 14. Checklist áp dụng

- [ ] Test nói rõ hành vi compile pass/fail hoặc chính sách warning.
- [ ] Compiler/JDK được tìm và khởi chạy đúng; lỗi môi trường không được tính là lỗi source mong đợi.
- [ ] Mã nguồn fixture được quản lý độc lập với main source set.
- [ ] Assertion chính dựa trên compilation result/exit code.
- [ ] Assertion lỗi sử dụng diagnostic có cấu trúc khi cần, không mặc định so toàn bộ message.
- [ ] Không khóa số lượng diagnostic, line/column và `getCode()` nếu không thuộc hợp đồng.
- [ ] Stderr và message vẫn được ghi để debug khi test thất bại.
- [ ] Warning, `-Werror`, annotation processor và tool invocation được xử lý theo từng mục tiêu riêng.
- [ ] Nếu thật sự cần snapshot formatter, có baseline toolchain/locale rõ ràng.
- [ ] Test có cả trường hợp source hợp lệ và source sai có chủ ý khi mục tiêu yêu cầu kiểm chứng hai chiều.

## Tài liệu chính thức

- [Java SE 17 — `javax.tools` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html)
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 — `Diagnostic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [Java SE 17 — `Diagnostic.Kind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html)
- [Java SE 17 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [JUnit 5 User Guide — Assertions](https://docs.junit.org/5.11.3/user-guide/index.html#writing-tests-assertions)

Nguyên tắc xuyên suốt: khi kiểm thử **biên dịch**, hãy assert **trạng thái và tín hiệu chẩn đoán có ý nghĩa**. Văn bản thông báo phục vụ con người và việc điều tra lỗi; chỉ biến nó thành expectation khi chính định dạng văn bản là yêu cầu sản phẩm.
