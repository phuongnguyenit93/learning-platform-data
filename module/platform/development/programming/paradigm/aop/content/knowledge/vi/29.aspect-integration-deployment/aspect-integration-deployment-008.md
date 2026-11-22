# Tạo bản dựng lặp lại và phát hiện thay đổi kết quả weaving trong AOP

## 1. Bài toán: cùng mã nguồn, weaving có còn giống nhau?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), *weaving* là quá trình tích hợp các **aspect** vào chương trình tại những **join point** được pointcut lựa chọn. Kết quả có thể là bytecode đã biến đổi, cấu trúc điều phối advice hoặc hành vi can thiệp tại thời điểm nạp lớp/chạy, tùy công cụ. Khi dự án phát triển, chỉ một thay đổi nhỏ ở pointcut, classpath hay phiên bản trình dệt có thể khiến advice áp dụng vào nhiều hoặc ít join point hơn trước.

Một **bản dựng lặp lại (reproducible build)** là bản dựng được tạo từ **cùng bộ đầu vào đã xác định** theo cùng quy trình và tạo ra **kết quả xác định** theo tiêu chí kiểm tra đã chọn. Với AOP cần xem ít nhất hai phương diện:

- **Kết quả nhị phân:** tập file `.class` và nội dung bytecode sau dệt có giống nhau từng byte không? Nếu đóng JAR, bản JAR có giống hệt từng byte không?
- **Kết quả weaving theo ngữ nghĩa:** cùng join point nào được áp dụng advice, thứ tự/precedence có đúng, các nhánh `before`, `around`, `after` và điều kiện động có giữ hành vi mong muốn không?

Hai tiêu chí khác nhau: **hash khác không nhất thiết nghĩa là chức năng đổi** (ví dụ thông tin debug hoặc metadata khác); ngược lại, **hash giống nhau không chứng minh mọi hành vi runtime giống nhau** nếu phiên bản runtime, agent, class loader hoặc cấu hình môi trường khác. Để phát hiện weaving drift đáng tin cậy, cần kết hợp kiểm tra artifact, danh sách join point được dệt và kiểm thử hành vi.

Bài tập trung vào AOP tổng quát, sử dụng **AspectJ** làm ví dụ một bộ công cụ dệt mã cụ thể. Các nguyên tắc khóa đầu vào, xây dựng sạch, fingerprint, baseline và CI có thể áp dụng cho những weaver khác sau khi điều chỉnh cách lấy thông tin.

## 2. Những thay đổi cần phát hiện

Một bộ phát hiện thay đổi weaving nên trả lời được các câu hỏi:

1. **Aspect nào đã tham gia?** Có aspect mới, bị loại khỏi build, bị thay đổi thứ tự áp dụng hoặc precedence không?
2. **Pointcut chọn những join point nào?** Một phương thức mới có vô tình khớp biểu thức wildcard rộng? Có lời gọi nằm ngoài phạm vi weaving?
3. **Bytecode có bị dệt khác?** Các class, method, synthetic helper, control flow và thông tin annotation/debug có thay đổi không?
4. **Hành vi có thay đổi?** Advice chạy ít/nhiều lần, trước/sau, `proceed` bị bỏ qua/lặp lại, exception hoặc dữ liệu đầu ra khác?
5. **Thay đổi có chủ ý không?** Mỗi khác biệt phải truy được về source commit, cấu hình, dependency, toolchain, phạm vi áp dụng hoặc một drift chưa được giải thích.

Ví dụ, một pointcut `execution(* demo..*(..))` có thể chọn thêm phương thức chỉ vì có class mới trong package `demo`. Nếu không kiểm tra các join point, lần build sau có thể thêm logging hoặc transaction boundary ngoài dự kiến dù file `.aj` không đổi. Trường hợp này là **weaving drift do thay đổi mã đầu vào**, không nhất thiết lỗi ở weaver.

## 3. Phân tầng tính lặp lại: từ byte đến ngữ nghĩa

| Tầng kiểm tra | Đầu ra dùng so sánh | Phát hiện tốt | Giới hạn |
| --- | --- | --- | --- |
| Nguồn và cấu hình | Commit, version lock, hash dependencies, flags, config | Đầu vào thay đổi ngoài ý muốn | Đầu vào giống chưa bảo đảm artifact giống |
| Tập file sau dệt | Danh sách đường dẫn tương đối các `.class` | Class mới, mất class, class phát sinh | Chưa cho biết nội dung bytecode |
| Hash của từng `.class` | SHA-256 theo đường dẫn ổn định | Thay đổi byte-for-byte sau dệt | Nhạy với debug info, compiler metadata |
| Artifact đóng gói | Hash JAR/WAR cùng metadata đóng gói | Thay đổi bytes của bản phát hành | Timestamp/thứ tự entry có thể tạo nhiễu |
| Weaving inventory | Tập sự kiện “aspect/advice → join point shadow” | Join point được chọn thêm, mất, thay đổi target | Cần chuẩn hóa log và xác minh log đầy đủ |
| Cấu trúc bytecode | `javap -c -p -l`, classfile parser/diff | Biến đổi control flow và call vào advice | Disassembly cũng có metadata/nhiễu biểu diễn |
| Kiểm thử hành vi | Output, thứ tự advice, count, exception, `proceed` | Sai khác quan sát được trong ca kiểm thử | Không chứng minh đầy đủ mọi đường chạy |

**Tiêu chuẩn nghiêm ngặt nhất** là cùng đầu vào và môi trường được khóa, build hai lần trong môi trường sạch cho **tập class và bytes giống nhau**, rồi xác nhận hành vi dự kiến. Trong thực tế, cũng cần khả năng *phân loại* thay đổi nếu việc đóng gói, vị trí source hoặc debug metadata không hoàn toàn quyết định.

### 3.1. “Giống từng byte” khác “giống chức năng”

Hai class có thể cho kết quả runtime giống nhau nhưng hash khác vì line number/local-variable tables, compiler-version metadata, constant pool, thứ tự thành viên hoặc mô tả source. Đừng loại bỏ mọi khác biệt của file `.class` thành “vô hại” khi chưa xác minh tác động.

Hai bản JAR cũng có thể hash khác dù mọi `.class` giống hệt, chỉ vì timestamp/entry order/MANIFEST thay đổi. Vì vậy, khi **JAR hash khác** nên tiếp tục so sánh tập entry và hash từng class; rồi mới xác định sự khác biệt là đóng gói hay weaving.

Ngược lại, **bytecode giống** chỉ xác nhận output compile/weave của lần đo là giống; load-time weaving hoặc cấu hình agent ở runtime vẫn có thể thay đổi kết quả thực thi.

## 4. Khóa toàn bộ đầu vào của quá trình dệt

Tập đầu vào của weaving rộng hơn mã `.aj`:

| Đầu vào | Ví dụ cần khóa/ghi nhận | Nguy cơ khi bỏ sót |
| --- | --- | --- |
| Source Java/aspect | Commit hash, trạng thái working tree, encoding UTF-8 | Mã gốc hoặc pointcut đổi |
| Binary input | Hash thư mục/JAR `-inpath` | Bytecode đầu vào đã thay đổi |
| Aspect binary | Phiên bản/hash `-aspectpath` nếu dùng binary aspects | Cùng Java source nhưng advice khác |
| Toolchain | JDK vendor/version, `ajc` và runtime tương thích, hệ build | Thay đổi compiler, bytecode, JIT/runtime |
| Build options | `-source`/`-target` hoặc `-17`, debug info, lint, weave options | Khác mức bytecode, metadata, thứ tự xử lý |
| Classpath | Chính xác bộ thư viện, phiên bản, thứ tự và dependency resolution | Type/method resolution khác, class trùng |
| Phạm vi weaving | Packages/classes include/exclude, cấu hình aspect, loader | Thêm/mất join point |
| Đóng gói | Resource, MANIFEST, timestamp, entry order, compression | JAR hash không ổn định |
| Runtime weaving | Agent args, `aop.xml` nếu dùng, class loader, thứ tự load | Kết quả dệt phát sinh khi nạp lớp thay đổi |
| Môi trường | OS, locale, timezone, đường dẫn, biến môi trường, filesystem | Non-determinism hoặc path/encoding drift |

**Lock dependency bằng hash/nội dung thực**, không chỉ tên phiên bản. Một repo artifact hoặc image tag có thể bị thay thế nếu không bảo đảm bất biến. Ghi nhận provenance để khi hash khác còn biết đã đổi input nào. Build sạch phải lấy từ cùng commit và cùng dependency cache/nội dung đã kiểm chứng.

Đặc biệt trong AspectJ, trình biên dịch `ajc` yêu cầu đưa vào đầy đủ nguồn hoặc bytecode cần dệt. Không nên mặc định nó tự tìm mọi source bị ảnh hưởng. Tránh đưa **output directory vào `-inpath`** trong lần build sau, vì có thể biến class đã dệt thành input ngoài ý muốn hoặc làm xuất hiện type trùng.

### 4.1. Weaving mode ảnh hưởng nơi đo

- **Compile-time weaving (CTW):** compiler nhận source Java/aspect rồi sinh class đã dệt. So sánh thư mục class output ngay sau build.
- **Post-compile/binary weaving:** weaver nhận class/JAR chưa dệt qua input như `-inpath` và aspect binary/source phù hợp. Cần lưu fingerprint **trước** và **sau** dệt, đồng thời xác minh không vô tình dệt lại class đã được dệt.
- **Load-time weaving (LTW):** class được biến đổi lúc class loader tải vào JVM. Artifact trên đĩa có thể vẫn là bản chưa dệt, vì vậy hash file đầu vào không phản ánh đầy đủ kết quả weaving thực tế. Cần ghi cấu hình agent/loader, sự kiện weaving runtime và các kiểm thử hành vi; nếu cần so bytes, phải có cơ chế thu bytecode sau biến đổi đáng tin theo bộ công cụ đang dùng.

Không gộp CTW và LTW hoặc dệt đi dệt lại cùng lớp nếu thiết kế không yêu cầu. Khả năng *reweavable* của một engine không thay thế việc kiểm soát đầu vào và tránh double-weaving ngoài ý muốn.

## 5. Một ví dụ AspectJ tối thiểu và quan sát được

Sử dụng JDK 17 trở lên, `ajc` hỗ trợ Java 17, thư viện `aspectjrt.jar` phù hợp. Ví dụ cố ý có đúng một method cần advice để dễ kiểm tra danh sách join point.

**Tệp `src/demo/Main.java`:**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        Calculator calculator = new Calculator();
        int result = calculator.add(2, 3);
        System.out.println("result=" + result);
    }
}

class Calculator {
    int add(int a, int b) {
        return a + b;
    }
}
```

**Tệp `src/demo/AuditAspect.aj`:**

```aspectj
package demo;

public aspect AuditAspect {
    before(int a, int b):
        execution(int demo.Calculator.add(int, int))
        && args(a, b) {
        System.out.println("audit add(" + a + "," + b + ")");
    }
}
```

Pointcut `execution` chọn thời điểm thực thi phương thức `Calculator.add`. `args(a,b)` bind hai đối số, giúp kiểm thử rằng advice chạy một lần khi gọi `add(2,3)`. Không có điều kiện động phụ thuộc thời gian hay nguồn dữ liệu ngoài.

**Cấu trúc nguồn:**

```text
project/
├── src/demo/Main.java
├── src/demo/AuditAspect.aj
└── lib/aspectjrt.jar
```

### 5.1. Hai lần build sạch, cấu hình như nhau

Chạy trong thư mục `project` trên Windows PowerShell (dùng hai thư mục output ban đầu trống, ví dụ từ một checkout mới). Cờ `-17` đặt source/target compliance Java 17; `-encoding UTF-8` cố định cách giải mã source; `-showWeaveInfo` hiển thị những vị trí advice được dệt.

```powershell
ajc -version
java -version

ajc -17 -encoding UTF-8 -g:lines,vars,source -showWeaveInfo -classpath "lib/aspectjrt.jar" -d build-A src/demo/Main.java src/demo/AuditAspect.aj
ajc -17 -encoding UTF-8 -g:lines,vars,source -showWeaveInfo -classpath "lib/aspectjrt.jar" -d build-B src/demo/Main.java src/demo/AuditAspect.aj

java -cp "build-A;lib/aspectjrt.jar" demo.Main
java -cp "build-B;lib/aspectjrt.jar" demo.Main
```

Với shell Unix, hai lệnh chạy cần đổi classpath delimiter từ `;` sang `:`. Kiểm soát trước rằng `build-A` và `build-B` **chưa chứa class/resource cũ**; nếu cần tái chạy, dùng hai thư mục output mới hoàn toàn hoặc một workspace tạm đã được xác minh. Không đưa `build-A` hay `build-B` vào `-inpath`.

**Stdout kỳ vọng của mỗi lần chạy `demo.Main`:**

```text
audit add(2,3)
result=5
```

Thông báo của `ajc -showWeaveInfo` có dạng phụ thuộc phiên bản, đường dẫn và cách xuất diagnostic; nó phục vụ kiểm tra vị trí weaving, không nên mặc định là output byte-for-byte ổn định. Cần giữ cả stdout/stderr và exit status của compiler trong hệ CI. Một thông báo warning không nhất thiết làm build thất bại; chính sách CI nên định nghĩa rõ loại warning phải xử lý.

### 5.2. Kiểm chứng nguồn và artifact

Ngay sau mỗi build:

1. Kiểm tra compiler exit status = 0; nếu build lỗi, **không** so sánh output dở dang.
2. Đếm và liệt kê toàn bộ file `.class` bằng đường dẫn **tương đối** so với `build-A`/`build-B`, sắp thứ tự ổn định.
3. Hash SHA-256 từng file `.class`; tên file có ở một phía mà không ở phía kia là khác biệt.
4. So sánh log weaving đã chuẩn hóa về đường dẫn/nội dung; xem advice nào được dệt tại method nào.
5. Chạy test hành vi trên cả hai output và so output/count/exception với oracle đã chấp thuận.

Nếu mọi class có hash giống nhau nhưng JAR khác, phân tích resource, manifest và metadata của archive riêng.

## 6. Công cụ Java 17 so sánh chính xác cây class sau weaving

Đoạn sau là **chương trình Java 17 độc lập**, không phụ thuộc AspectJ, dùng để so sánh toàn bộ tập `.class` theo **đường dẫn tương đối và SHA-256**. Khác với so kích thước file hoặc timestamp, nó phát hiện cả class thêm/mất và khác một byte trong file. Đặt ở **`ClassTreeDiff.java`** trong thư mục `project`.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public class ClassTreeDiff {
    private static Map<String, String> inventory(Path root)
            throws Exception {
        Map<String, String> hashes = new TreeMap<>();

        try (Stream<Path> paths = Files.walk(root)) {
            for (Path file : paths
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".class"))
                    .toList()) {
                String relative = root.relativize(file)
                        .toString().replace('\\', '/');
                byte[] bytes = Files.readAllBytes(file);
                byte[] digest = MessageDigest.getInstance("SHA-256")
                        .digest(bytes);
                hashes.put(relative, HexFormat.of().formatHex(digest));
            }
        }
        return hashes;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java ClassTreeDiff <left> <right>");
            System.exit(2);
        }

        Map<String, String> left = inventory(Path.of(args[0]));
        Map<String, String> right = inventory(Path.of(args[1]));

        Set<String> paths = new TreeSet<>(left.keySet());
        paths.addAll(right.keySet());

        int changed = 0;
        for (String path : paths) {
            if (!Objects.equals(left.get(path), right.get(path))) {
                String kind = !left.containsKey(path) ? "ADDED"
                        : !right.containsKey(path) ? "REMOVED"
                        : "CHANGED";
                System.out.println(kind + " " + path);
                changed++;
            }
        }

        if (changed > 0) {
            System.out.println("FAIL: differing class files=" + changed);
            System.exit(1);
        }

        System.out.println("PASS: .class trees byte-identical");
    }
}
```

Lệnh chạy:

```powershell
javac ClassTreeDiff.java
java ClassTreeDiff build-A build-B
```

Nếu hai bản chứa tập class giống nhau và bytes từng class giống nhau, stdout chính xác:

```text
PASS: .class trees byte-identical
```

Nếu có khác biệt, chương trình in `ADDED`, `REMOVED` hoặc `CHANGED` kèm đường dẫn class, rồi thông báo tổng số và thoát với **exit code 1**. Nếu gọi thiếu tham số, thoát **2**. Hệ CI cần xử lý exit code khác 0 thành kết quả thất bại.

**Giới hạn kỹ thuật:** chương trình này chỉ kiểm tra file `.class`, chưa so sánh resource, native libraries hoặc JAR packaging; nó không tự nói phần bytecode khác thuộc logic advice, debug attributes hay compiler. Chỉ dùng đường dẫn output **tin cậy**, tương đương nhau và đã được tạo sạch; với artifact quá lớn, có thể chuyển sang đọc file theo luồng để giảm bộ nhớ, nhưng cùng nguyên tắc hash.

## 7. So sánh weaving theo ngữ nghĩa, không dừng ở hash

Để phát hiện một pointcut tự mở rộng phạm vi, cần một **weaving inventory** được sinh từ cùng lần build. Với AspectJ, `-showWeaveInfo` đưa ra thông tin về weaving, nhưng chuỗi log thô có thể khác bởi đường dẫn tuyệt đối, vị trí source, phiên bản compiler hoặc thứ tự thông báo. Quy trình tốt:

1. Thu đủ diagnostics của từng lần `ajc`, bao gồm warnings/errors và weave info.
2. Chuẩn hóa **chỉ những phần không mang ngữ nghĩa** như tiền tố đường dẫn workspace và định dạng đường dẫn. Giữ nguyên tên aspect, advice kind, pointcut/method signature, tên class, vị trí join point và thông báo cảnh báo.
3. Chuyển thành một tập record có cấu trúc nếu parser của phiên bản compiler cho phép. Ví dụ record khái niệm: `aspect=demo.AuditAspect | advice=before | kind=execution | target=demo.Calculator.add(int,int)`.
4. Sort ổn định, giữ số lần xuất hiện nếu nhiều shadow thực sự khác nhau; tránh biến dữ liệu thành set rồi vô tình xóa các bản ghi trùng có ý nghĩa.
5. Lưu manifest đã được review làm **baseline**. Diff các record giữa nhánh hiện tại và baseline: **added**, **removed**, **changed**. Mỗi thay đổi cần lý do rõ ràng.
6. Nếu format log thay đổi khi nâng compiler, nâng phiên bản parser cùng bộ kiểm thử; đừng dùng regex quá rộng làm mất thông tin quan trọng.

**Lưu ý:** record trên là *định dạng inventory đề xuất*, không phải output nguyên văn cố định của `ajc`. Một số weaver không cung cấp danh sách đầy đủ các join point/guard như mong muốn; khi đó phải kết hợp bytecode inspection và test hành vi. `-showWeaveInfo` không phải bằng chứng đủ về điều kiện runtime như `if(...)` hoặc `cflow(...)`.

### 7.1. Baseline cho thay đổi có chủ đích

Ví dụ pull request chỉnh pointcut từ:

```aspectj
execution(int demo.Calculator.add(int, int))
```

sang biểu thức rộng hơn:

```aspectj
execution(int demo.Calculator.*(int, int))
```

Nếu có thêm `subtract(int,int)`, manifest sẽ có thêm target. Đó có thể là chủ ý hoặc bug. CI nên hiển thị diff cùng nội dung PR để người review quyết định. **Không tự động “chấp nhận baseline mới” chỉ để pipeline xanh**; baseline phải được cập nhật cùng thay đổi ngữ nghĩa đã được kiểm tra.

Với các around advice, kiểm thử cần ghi cả số lần `proceed`, việc bỏ qua gốc, kết quả trả về và exception path. Một manifest nói rằng advice *có thể* dệt tại join point không đảm bảo advice luôn chạy nếu pointcut còn điều kiện động.

## 8. Kiểm tra bytecode sau dệt khi phát hiện hash khác

Khi `ClassTreeDiff` báo `CHANGED demo/Calculator.class`:

1. Xác nhận input class/source có giống nhau trước weaving.
2. So sánh phiên bản `ajc`, JDK, compiler options và aspect bytecode.
3. Disassemble hai class để xem thân method và helper khác nhau:

```powershell
javap -classpath build-A -c -p -l demo.Calculator > calculator-A.txt
javap -classpath build-B -c -p -l demo.Calculator > calculator-B.txt
```

4. Xem thay đổi nằm ở lời gọi vào advice, nhánh điều khiển, kiểu/metadata hay chỉ line table và local variables.
5. So inventory weaving và chạy test hành vi tương ứng; nếu quanh `proceed` hoặc precedence thay đổi, thêm ca test không chỉ hash.

`javap -c -p -l` là công cụ chẩn đoán, **không** phải canonicalizer bytecode được bảo đảm. Chuỗi disassembly, constant-pool indices hoặc debug mapping có thể khác. Việc tự loại bỏ tất cả dòng metadata khi diff có thể che khuất một lỗi cần phát hiện. Nếu cần so ở mức classfile chuyên nghiệp, dùng một parser AST bytecode có kiểm soát phiên bản và phân loại vùng khác nhau rõ ràng.

### 8.1. Nên theo dõi gì ngoài class hash?

- Số lượng class đã dệt và số join point shadow được advice.
- Những aspect/advice mới, mất, hoặc thay đổi áp dụng.
- Kích thước class/method tăng mạnh, helper hoặc synthetic members mới.
- Warnings về join point không match, advice không được áp dụng, classpath và type resolution.
- Đường đi của exception, `around`/`proceed` và số lần advice gọi thực tế.
- Class loader, thứ tự nạp và agent setup nếu weaving xảy ra lúc load.

Không quy mọi thay đổi kích thước class thành regression; phải phân tích phần mới sinh có đúng yêu cầu hay không.

## 9. Thiết kế pipeline CI phát hiện weaving drift

Một pipeline có thể gồm sáu chặng:

```text
Checkout commit cố định
          |
Kiểm tra toolchain/dependency lock + hash
          |
Clean build + weave (lưu log)
          |
Tạo class manifest + hash / đóng artifact
          |
So woven targets + chạy test AOP
          |
Diff với baseline đã duyệt và quyết định pass/fail
```

Thực hành đề xuất:

1. **Preflight:** xác nhận commit, JDK, `ajc`, runtime, classpath và cấu hình; fail nếu thiếu dependency hoặc có file trùng type. Đảm bảo output trống.
2. **Rebuild lặp lại:** chạy **hai clean build độc lập** với cùng lock và cùng môi trường; so `.class` hash để phát hiện tính không quyết định. Với yêu cầu rất cao, lặp lại trên runner khác nhưng giữ môi trường được mô tả và phân tích khác biệt OS.
3. **Artifact diff với bản chuẩn:** so tập class, hash, weaving inventory với commit/baseline được review; không nhầm “hai build hiện tại giống nhau” với “không thay đổi so baseline”.
4. **Weaving contract tests:** dùng testcase kiểm tra advice có/không khớp, đúng số lần, thứ tự và dữ liệu; cả `return`, `throw`, điều kiện động true/false, overloaded methods và kế thừa.
5. **Đóng gói:** kiểm tra thành phần phát hành; thiết lập timestamps/thứ tự entry/MANIFEST xác định nếu muốn **reproducible JAR bytes**; so từng class khi JAR hash khác.
6. **Phê duyệt thay đổi:** đính kèm báo cáo added/removed/changed joins, hash khác và lý do; cập nhật baseline chỉ sau khi xem xét đúng ngữ nghĩa.

Một policy minh họa:

| Kiểm tra | Kết quả | Quyết định |
| --- | --- | --- |
| Hai clean builds cùng đầu vào nhưng class hash khác | Build chưa reproducible ở mức bytes | Fail bước lặp lại, tìm nguồn bất định |
| Build mới khác baseline và có join point không mong muốn | Weaving drift nguy hiểm | Fail, sửa pointcut/phạm vi |
| Hash khác nhưng cùng weaving inventory | Cần phân tích bytecode/metadata | Review thay đổi toolchain/debug/logic |
| Manifest thay đổi có chủ ý, test đúng, baseline được duyệt | Thay đổi được kiểm soát | Có thể cập nhật baseline |
| Weaving inventory giống nhưng test thứ tự advice lỗi | Hành vi sai | Fail; inventory chưa bao phủ semantic |
| Tất cả class hashes giống, nhưng LTW agent config khác | Runtime có thể khác | Bắt buộc kiểm tra cấu hình và test LTW |

**Phân biệt hai phép thử quan trọng:** kiểm tra reproducibility so **A với B từ cùng commit**, còn regression detection so **commit mới với baseline đã duyệt**. Một thay đổi pointcut có chủ ý sẽ khiến artifact khác baseline nhưng vẫn có thể build lặp lại ổn định.

## 10. Thử nghiệm biến đổi để chứng minh hệ thống phát hiện tốt

Để xác minh pipeline không chỉ báo PASS do chạy sai lớp hoặc thiếu parser, hãy chủ động tạo các tình huống kiểm thử trên branch độc lập:

**Ca 1 — không đổi input:** hai thư mục output sạch có cùng source/aspect/toolchain. Kỳ vọng cùng stdout và cùng class hash nếu build quyết định.

**Ca 2 — đổi advice body:** thay `System.out.println("audit add(" + a + "," + b + ")");` bằng thông báo khác. Kỳ vọng class hash đổi; test stdout thay; nếu không thay, kiểm tra build đang chạy artifact cũ.

**Ca 3 — thay pointcut không còn match:** đổi `add` thành một chữ ký khác không tồn tại. Kỳ vọng không còn dòng `audit add(2,3)` ở runtime; weaving inventory mất record cũ. Compiler có thể phát ra warning phù hợp tùy điều kiện/phiên bản.

**Ca 4 — mở rộng pointcut:** thêm một method vào loại target hoặc nới wildcard. Kỳ vọng manifest cho thấy join point mới nếu method thật sự nằm trong phạm vi weaving.

**Ca 5 — build input chưa sạch:** lẫn class đã dệt trước vào `-inpath` hoặc output. Kỳ vọng preflight phát hiện input không đúng provenance; không sử dụng drift report từ một build bị nhiễm để cập nhật baseline.

**Ca 6 — thay đổi chỉ đóng gói:** thay timestamp hoặc thứ tự entry JAR nhưng giữ class bytes. Kỳ vọng JAR hash khác, class hashes giống; cần sửa bước archive normalization thay vì sửa aspect.

**Ca 7 — load-time weaving:** giữ source/JAR nguyên nhưng thay tập include/exclude hoặc agent/class loader. Kỳ vọng runtime weaving event/test có thể thay đổi; chỉ so disk class là không đủ.

Các ca test này là cách đánh giá *khả năng phát hiện* của kiểm soát chất lượng, không phải khuyến nghị đưa biến đổi thử nghiệm vào nhánh phát hành.

## 11. Các yếu tố gây nondeterminism thường bị bỏ sót

### 11.1. Thời gian, đường dẫn và môi trường

Timestamp và thứ tự ZIP entry làm JAR hash khác; absolute source path và debug metadata đôi khi gây khác file `.class` khi build ở hai đường dẫn khác nhau. Locale/charset hoặc timezone cũng có thể ảnh hưởng nếu build scripts sinh mã/metadata dựa trên chúng. Cố định locale/encoding cần thiết, đồng thời kiểm tra **thực nghiệm** chứ không mặc định mọi compiler đều nhúng các trường này.

### 11.2. Input order và duplicate classes

Classpath có class trùng tên hoặc dependency giải quyết phiên bản không xác định dễ tạo kết quả khác. Cố định thứ tự classpath và source list, kiểm soát dependency hashes, không dùng wildcard lấy “phiên bản mới nhất” trong build yêu cầu tái lập. Khi có `-aspectpath`, dùng aspect binary đúng phiên bản compiler hỗ trợ và runtime classpath tương ứng.

### 11.3. Incremental build so với clean build

Incremental build có thể tái sử dụng class cũ, bỏ sót thay đổi phụ thuộc hoặc giữ artifact không còn thuộc source. Dùng **clean build** để làm oracle tái lập; sau đó kiểm tra riêng incremental build có tạo artifact tương đương clean build khi cùng commit. Nếu không tương đương, điều tra build cache, dependency graph hoặc tính đúng của invalidation trước khi chấp nhận incremental output.

### 11.4. Advice ordering và điều kiện runtime

Hai bản cùng tập pointcut target vẫn có thể khác precedence hoặc cách bind đối số. Tập target không bao quát hoàn toàn **semantics**. Pointcut `if(...)`, `cflow(...)` và kiểm tra kiểu runtime cần testcase true/false, nested calls, đa luồng nếu cần. Với `around`, xác minh `proceed` có được gọi một hoặc nhiều lần, thay đổi tham số, exception và kết quả.

### 11.5. Output đồng nhất không đủ để khẳng định hệ thống đúng

Nếu cả hai clean builds cùng sai nhưng giống nhau từng byte, reproducibility vẫn PASS. Cần test chức năng, cấu hình, chính sách precedence và baseline join point để bảo đảm **đúng**. Không nhập nhằng “reproducible” với “verified correct”.

## 12. Thu thập provenance và bằng chứng phát hành

Một record build nên có:

```text
build_id: release-2026-example
source_commit: <exact-commit-sha>
java_runtime: <vendor + version>
aspect_compiler: <ajc version>
aspect_runtime: <artifact version + sha256>
compiler_options: <-17, encoding, debug, weave flags>
compile_classpath: <ordered coordinates + content hashes>
binary_inpath: <ordered input paths + hashes, if any>
aspectpath: <ordered artifact hashes, if any>
weaver_config: <hash and content identity>
weaving_mode: <compile-time | binary | load-time>
output_class_manifest: <stable paths + sha256>
weaving_inventory: <normalized record set>
behavior_test_result: <suite, results, environment>
archive_metadata_policy: <timestamp/order/manifest rules>
```

Đây là **mẫu cấu trúc minh họa**, không phải một file tiêu chuẩn được AspectJ sinh tự động. Các giá trị thực phải đến từ build pipeline; dấu ngoặc nhọn chỉ trường cần điền khi triển khai. Không đặt đường dẫn nội bộ bí mật, token registry hoặc thông tin nhạy cảm vào log công khai.

Nếu build artifact được ký hoặc phát hành qua registry, liên kết manifest và kết quả kiểm tra với digest của artifact. Signature/provenance bảo đảm truy vết và toàn vẹn phân phối; nó **không thay thế** việc xác nhận pointcut và advice đúng ý định.

## 13. Những lỗi phổ biến

- **“Cùng commit là đủ để reproducible.”** Chưa đủ: toolchain, dependencies, flags, weaving mode, classpath và môi trường có thể khác.
- **“Hai JAR hash khác nghĩa là aspect đã dệt khác.”** Chưa chắc: có thể chỉ timestamp, entry order hoặc resources.
- **“Class hash giống nghĩa là LTW không thay đổi.”** Sai: dệt lúc nạp lớp và cấu hình runtime có thể khác mà disk bytes vẫn giống.
- **“Log weaving giống nghĩa là runtime luôn giống.”** Không: dynamic pointcut, order/precedence và dữ liệu runtime vẫn cần kiểm thử.
- **“Chỉ so kích thước class là đủ.”** Không: khác bytes cùng kích thước vẫn xảy ra; dùng SHA-256 theo đường dẫn.
- **“Chỉ so output của hai build hiện tại là phát hiện regression.”** Không: cần so với baseline đã được duyệt.
- **“Mỗi thay đổi log có thể chuẩn hóa bỏ đi cho đỡ nhiễu.”** Nguy hiểm: có thể che mất advice target mới/mất hoặc cảnh báo mới.
- **“Incremental build luôn tương đương clean build.”** Cần thử và xác minh cache invalidation.
- **“`-inpath` có thể chứa output đã dệt từ vòng trước cho tiện.”** Dễ gây input trùng/không rõ provenance; tránh nếu không có thiết kế reweaving rõ ràng.
- **“Cứ cập nhật golden file khi CI đỏ.”** Thay đổi ngữ nghĩa phải có review và test trước khi cập nhật baseline.

## 14. Checklist áp dụng cho dự án thực

1. **Khóa đầu vào:** source revision, aspect, JDK, compiler/weaver version, dependencies hashes, options, classpath order, include/exclude.
2. **Chọn weaving mode:** CTW, binary hay LTW; xác định nơi có bytecode sau dệt để so sánh.
3. **Build sạch ít nhất hai lần:** output độc lập, exit code thành công; so class inventory và SHA-256.
4. **Nếu đóng gói:** so archive metadata và thiết lập timestamp/order ổn định; phân biệt JAR drift với class drift.
5. **Thu join point evidence:** `-showWeaveInfo` hoặc công cụ tương đương, chuẩn hóa đúng các trường vô hại rồi diff với golden baseline.
6. **Chạy behavior tests:** advice count, precedence, dynamic true/false, `around`/`proceed`, return/exception, đúng target.
7. **Điều tra khác biệt:** hash → cấu trúc bytecode → woven targets → runtime behavior; xác minh source và tooling trước.
8. **Cổng CI:** fail khi build không lặp lại, target drift ngoài ý muốn hoặc behavior sai; chỉ duyệt baseline mới sau review.
9. **Gắn provenance:** bảo quản manifest, logs, toolchain identity và digest artifact để truy vết.
10. **Định kỳ thử ca biến đổi có chủ đích:** bảo đảm hệ thống có thể thật sự bắt thêm/mất join point.

**Kết luận:** một bản dựng AOP đáng tin cần **đầu vào đã khóa**, **môi trường build sạch**, **bytecode fingerprint**, **bằng chứng join point được dệt**, và **test hành vi**. So sánh byte-for-byte giúp phát hiện tính không quyết định; weaving inventory và test giúp xác định thay đổi về ngữ nghĩa. Chỉ khi tách hai khía cạnh này, ta mới biết một khác biệt là drift đáng lo, thay đổi có chủ ý hay đơn thuần khác biệt đóng gói.

## Tài liệu tham khảo

- Eclipse AspectJ Development Guide — `ajc`, `-inpath`, `-aspectpath`, `-showWeaveInfo`, `-argfile`, `-17`, `-encoding` và `-d`: https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html
- Eclipse AspectJ Programming Guide — pointcut, advice, weaving và join point semantics: https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html
- AspectJ Load-Time Weaving documentation: https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html
- Reproducible Builds — tổng quan nguồn nondeterminism, build path, timestamps và archive normalization: https://reproducible-builds.org/docs/
