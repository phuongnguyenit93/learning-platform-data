# Đóng gói và kiểm tra tạo tác đã dệt trong AOP

## 1. Mục tiêu và phạm vi

Trong **Aspect-Oriented Programming (AOP)**, *weaving* là quá trình kết hợp logic của aspect với mã tại các *join point* phù hợp. Khi quá trình này diễn ra trước khi ứng dụng chạy, kết quả thường là các tệp `.class` hoặc JAR đã thay đổi: **tạo tác đã dệt (woven artifact)**. Việc biên dịch không báo lỗi chưa đủ để kết luận tạo tác giao cho môi trường chạy đã được weave đúng, mang đủ phụ thuộc và thực hiện advice đúng chỗ.

Bài này hướng dẫn:

- Phân biệt **artifact đã dệt**, **artifact chứa aspect nhưng chưa dệt** và **cấu hình load-time weaving**.
- Xác định đầu vào/đầu ra và thứ tự đúng của quy trình **compile → weave → package → verify → test → publish**.
- Đóng gói JAR có bytecode đã được weave; kiểm tra nội dung JAR, bytecode và hành vi runtime.
- Giữ nguyên tài nguyên, metadata, hợp đồng nhị phân và phụ thuộc cần thiết khi xử lý JAR sẵn có.
- Thiết kế kiểm tra trong CI để phát hiện thiếu weaving, sai pointcut, nạp nhầm artifact, thiếu thư viện runtime hoặc tác dụng advice không mong muốn.

Ví dụ dùng **Java 17+** và compiler/weaver **AspectJ độc lập** để minh họa cơ chế AOP bằng bytecode. Các nguyên tắc đóng gói, kiểm thử và truy vết đầu ra cũng áp dụng khi dùng công cụ AOP khác có cơ chế weaving tương tự.

## 2. “Đã dệt” có nghĩa gì ở từng cách triển khai?

Một aspect định nghĩa **điều kiện khớp (pointcut)** và **hành vi bổ sung (advice)**. Không phải cứ có tệp aspect trong JAR là đã chèn được advice vào mọi lớp mong muốn.

| Cách triển khai | Tại thời điểm build có gì? | Điều kiện chạy đúng | Điểm cần kiểm tra |
|---|---|---|---|
| **Compile-time weaving (CTW)** | Compiler biên dịch nguồn Java/aspect và tạo class đã được weave | Chạy đúng class đã weave, có thư viện runtime cần thiết | Weave log, classfile, JAR cuối và smoke test |
| **Post-compile / binary weaving** | Class/JAR đã biên dịch trước được biến đổi thành **đầu ra mới** | Đóng gói **đầu ra đã biến đổi**, không nhầm bản input | Giữ tài nguyên, phát hiện trùng class, kiểm tra class khác biệt và runtime |
| **Load-time weaving (LTW)** | Artifact ứng dụng có thể vẫn chứa bytecode chưa weave; aspect và cấu hình phải sẵn có | Agent/transformer được kích hoạt trước khi loader định nghĩa lớp cần weave | Cấu hình agent, cách nạp lớp, log weaving runtime và test bằng lệnh chạy thật |
| **Interception qua proxy lúc chạy** | Artifact chứa mã nghiệp vụ và cơ chế tạo proxy/interceptor | Các lời gọi phải đi qua proxy/interception boundary | Kiểm tra luồng gọi và hành vi advice; không thể suy ra “class đã weave” chỉ từ proxy |

Đối với CTW/binary weaving, đầu ra cần được coi là **một sản phẩm build riêng**. Thư mục lớp chưa weave không được tự động ghi đè lên thư mục lớp đã weave trong bước đóng gói sau cùng.

### 2.1. Tạo tác là tập hợp nhiều thành phần

Một gói phát hành có thể gồm:

- `.class` nghiệp vụ đã được weave.
- `.class` của aspect hoặc helper được compiler sinh ra.
- File cấu hình, tài nguyên, `META-INF`, service descriptors và manifest phù hợp.
- Phụ thuộc runtime tương ứng với kỹ thuật weaving đang dùng.
- Metadata phát hành: phiên bản mã nguồn, JDK/toolchain, phiên bản weaver, phiên bản phụ thuộc và checksum.

**Chỉ kiểm tra thấy tên aspect trong JAR là chưa đủ.** Một advice có thể không khớp bất kỳ join point nào; hoặc JAR chứa aspect nhưng lớp mục tiêu vẫn là bytecode chưa biến đổi.

## 3. Quy trình build có thể kiểm chứng

Một pipeline dễ kiểm tra nên đi theo chiều một hướng:

```text
Mã nguồn nghiệp vụ + mã aspect + cấu hình pointcut
                         |
                         v
                 Compile / Weave
                         |
                  Weave info, lỗi
                         |
                         v
           Thư mục output woven sạch
                         |
                         v
           Package → application-woven.jar
                         |
          +--------------+---------------+
          |                              |
          v                              v
     Kiểm tra tĩnh                  Kiểm tra chạy
  jar/list/javap/metadata       expected advice + nghiệp vụ
          |                              |
          +--------------+---------------+
                         |
                    CI xác nhận
                         |
                         v
                Ký / xuất bản / triển khai
```

Để pipeline đáng tin cậy:

1. **Chốt đầu vào:** version mã nguồn, cấu hình pointcut, weaver, JDK và dependency. Cùng nguồn nhưng khác cấu hình weaving có thể sinh class khác nhau.
2. **Tạo output sạch, tách biệt:** ví dụ `build/woven-classes`. Tránh để class không còn trong source hoặc đầu ra lần build trước lọt vào JAR.
3. **Kiểm tra kết quả weaving:** compiler thành công, các join point quan trọng xuất hiện trong weave report, không có cảnh báo phạm vi hoặc lỗi classpath bị bỏ qua.
4. **Đóng gói sau weaving:** lấy class từ đúng output đã weave, bổ sung tài nguyên/manifest theo hợp đồng triển khai.
5. **Kiểm tra JAR cuối**, rồi chạy test sử dụng **chính JAR đó**. Test chỉ chạy class tại thư mục build không đủ để chứng minh JAR phát hành đúng.
6. **Ký và phát hành sau cùng:** nếu có ký JAR, thay đổi bytecode hoặc cấu trúc entry sau khi ký làm chữ ký không còn phù hợp.

## 4. Ví dụ end-to-end: weave, đóng gói và chạy JAR

Ví dụ này dùng cú pháp AspectJ để dệt **before advice** vào một phương thức Java. Nó không dùng bất kỳ framework ứng dụng nào.

### 4.1. Cấu trúc mã nguồn

```text
sample/
└── src/
    └── demo/
        ├── Calculator.java
        ├── Main.java
        └── AuditAspect.aj
```

Tệp `src/demo/Calculator.java`:

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int a, int b) {
        return a + b;
    }
}
```

Tệp `src/demo/Main.java`:

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + Calculator.sum(3, 4));
    }
}
```

Tệp `src/demo/AuditAspect.aj`:

```java
package demo;

public aspect AuditAspect {
    before(): execution(public static int demo.Calculator.sum(int, int)) {
        System.out.println("AOP: before sum");
    }
}
```

Pointcut trên chỉ nhắm vào **thực thi** `Calculator.sum(int,int)` có đúng modifier, kiểu trả về và tham số đã khai báo. `before` chạy trước thân phương thức mỗi khi execution join point được thực hiện; mã nghiệp vụ không cần gọi aspect bằng tay.

### 4.2. Công cụ và phiên bản

Cần JDK 17+ có `java`, `javac`, `jar`, `javap`; môi trường ví dụ sử dụng **AspectJ 1.9.24** (hỗ trợ Java 17). `aspectjtools` chứa compiler/weaver; `aspectjrt` là thư viện runtime cho lớp đã weave. Giữ cùng phiên bản AspectJ cho các thành phần liên quan.

Các lệnh sau dành cho terminal kiểu POSIX (`bash` hoặc tương đương), thực thi tại thư mục `sample`. Tải dependency từ Maven Central, sau đó dùng `ajc` để biên dịch và weave:

```bash
mkdir -p tools build/woven-classes

curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjtools/1.9.24/aspectjtools-1.9.24.jar \
  -o tools/aspectjtools-1.9.24.jar
curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjrt/1.9.24/aspectjrt-1.9.24.jar \
  -o tools/aspectjrt-1.9.24.jar

java -cp tools/aspectjtools-1.9.24.jar \
  org.aspectj.tools.ajc.Main \
  -17 -encoding UTF-8 \
  -classpath tools/aspectjrt-1.9.24.jar \
  -showWeaveInfo \
  -d build/woven-classes \
  src/demo/Calculator.java \
  src/demo/Main.java \
  src/demo/AuditAspect.aj
```

`-17` chọn mức source/target Java 17. `-showWeaveInfo` yêu cầu compiler thông báo join point được weave. Cần **đọc và lưu** báo cáo này trong CI: mã thoát `0` không chứng minh một pointcut cụ thể thật sự khớp. Dòng weave info có định dạng phụ thuộc phiên bản nên không nên viết kiểm thử quá phụ thuộc câu chữ đầy đủ của log.

Cần loại bỏ output cũ trước mỗi lần build độc lập; ví dụ lệnh trên giả định đang làm việc trong cây build mới. CI cần thực hiện bước clean riêng theo cơ chế của hệ build trước khi chạy lệnh.

### 4.3. Đóng gói class đã weave

```bash
jar --create \
  --file build/calculator-woven.jar \
  -C build/woven-classes .
```

`-C build/woven-classes .` đưa toàn bộ class bên dưới thư mục woven vào JAR với đường dẫn tương đối như `demo/Calculator.class`. Không đóng gói lại từ `src` hay `build/plain-classes`.

**Phân biệt compiler và thư viện runtime:** artifact `calculator-woven.jar` chứa ứng dụng và aspect đã biên dịch; nó **không tự bao gồm** `aspectjrt`. Nếu muốn phát hành một JAR độc lập hoàn toàn, cần thiết kế gói phụ thuộc thích hợp (fat JAR, phân phối nhiều JAR, manifest classpath hoặc cơ chế launcher), và kiểm chứng cách xử lý resource/metadata. Không tự động coi một JAR thường là executable JAR.

### 4.4. Kiểm tra nội dung và bytecode của chính JAR

```bash
jar --list --file build/calculator-woven.jar

javap -classpath build/calculator-woven.jar \
  -c -p demo.Calculator
```

Danh sách thành phần phải có ít nhất:

```text
demo/Calculator.class
demo/Main.class
demo/AuditAspect.class
```

JAR cũng có thể chứa entry manifest và các class/metadata compiler bổ sung. Thứ tự của `jar --list` không phải bằng chứng weaving.

Trong output `javap -c -p`, quan sát bytecode **phương thức `demo.Calculator.sum`**: mã đã weave thường chứa lời gọi phụ trợ tới aspect/advice hoặc instruction bổ sung. Tên helper và cách tổ chức bytecode do phiên bản weaver quyết định nên **không yêu cầu một mẫu instruction cứng**. Nếu bytecode không đổi, điều tra pointcut, compiler input, classpath và vị trí output; tuy nhiên chỉ nhìn disassembly vẫn chưa chứng minh toàn bộ semantics đúng.

### 4.5. Chạy JAR phát hành và xác nhận stdout

```bash
java -cp "build/calculator-woven.jar:tools/aspectjrt-1.9.24.jar" \
  demo.Main
```

Đầu ra của ví dụ:

```text
AOP: before sum
RESULT=7
```

Thứ tự này chứng minh cả **before advice chạy trước thân `sum`** và **kết quả nghiệp vụ vẫn là 7**. Đây là kiểm tra chức năng, không phải benchmark. Trên Windows dùng dấu chấm phẩy `;` thay cho dấu hai chấm `:` làm ký tự phân cách classpath.

Có thể kiểm tra tự động trong terminal POSIX:

```bash
actual=$(java -cp \
  "build/calculator-woven.jar:tools/aspectjrt-1.9.24.jar" \
  demo.Main)
expected=$(printf 'AOP: before sum\nRESULT=7')
test "$actual" = "$expected"
```

Lệnh `test` trả mã thoát khác `0` khi output không khớp. Đừng chỉ kiểm tra có chuỗi `RESULT=7`: nếu thiếu advice, nghiệp vụ vẫn có thể trả 7 và bài kiểm thử quá yếu sẽ báo pass giả.

### 4.6. So sánh với artifact chưa weave để tìm lỗi nhầm đầu ra

Có thể biên dịch riêng **chỉ hai lớp Java nghiệp vụ** thành một bản baseline:

```bash
mkdir -p build/plain-classes

javac -d build/plain-classes \
  src/demo/Calculator.java src/demo/Main.java

jar --create \
  --file build/calculator-plain.jar \
  -C build/plain-classes .

java -cp build/calculator-plain.jar demo.Main
```

Kết quả baseline:

```text
RESULT=7
```

Nếu deploy artifact mang tên `calculator-woven.jar` mà output lại giống baseline, các nguyên nhân thường gặp là **đóng gói nhầm thư mục**, **pointcut không khớp**, **class được load từ một JAR khác**, hoặc **advice không có trong quá trình weaving**.

## 5. Binary weaving khi chỉ có class/JAR đã biên dịch

Khi nhận thư viện ở dạng bytecode, có thể weave bằng compiler/weaver hỗ trợ **`-inpath`** (class directory hoặc JAR đầu vào) rồi ghi ra output riêng. Ví dụ tiếp nối bản baseline ở trên:

```bash
mkdir -p build/binary-woven-classes

java -cp tools/aspectjtools-1.9.24.jar \
  org.aspectj.tools.ajc.Main \
  -17 -encoding UTF-8 \
  -classpath tools/aspectjrt-1.9.24.jar \
  -inpath build/plain-classes \
  -showWeaveInfo \
  -d build/binary-woven-classes \
  src/demo/AuditAspect.aj

jar --create --file build/calculator-binary-woven.jar \
  -C build/binary-woven-classes .

java -cp "build/calculator-binary-woven.jar:tools/aspectjrt-1.9.24.jar" \
  demo.Main
```

Output mong đợi vẫn là:

```text
AOP: before sum
RESULT=7
```

**`-inpath`** nhập class đã biên dịch làm đầu vào để weave; **`-classpath`** giúp compiler phân giải type/phụ thuộc, không tự có nghĩa tất cả class trên classpath sẽ được weave. **`-aspectpath`** dùng khi aspect đã được biên dịch ở dạng binary/library và phải được áp dụng lên các lớp đầu vào; khi đó cần cung cấp các thư viện aspect tương ứng trên runtime classpath.

Nếu input là **JAR có resource hoặc manifest riêng**, cần kiểm tra lại chính các tài nguyên đó trong output; ví dụ tối giản ở trên chỉ chứa class nên không chứng minh việc bảo toàn một JAR sản xuất phức tạp. Binary weaving cũng có thể thay đổi nội dung class làm chữ ký JAR gốc không còn hợp lệ. Không sử dụng lại chữ ký cũ như thể các byte đã được ký vẫn nguyên vẹn.

### 5.1. Những câu hỏi về input JAR cần trả lời

- Có những class nào thực sự thuộc phạm vi weaver? Liệu class phụ thuộc bên ngoài chỉ nằm trên classpath hay là input cần weave?
- Có tài nguyên `META-INF/services`, cấu hình, manifest `Main-Class`/`Class-Path`, module descriptor hoặc lớp multi-release hay không?
- Output có ghi đè input, đưa trùng phiên bản class hoặc để sót class cũ không?
- Có dùng **shading/relocation** sau weaving khiến tên package, annotation, signature hoặc pointcut khác với lúc build?
- Có aspect binary cần hiện diện lúc chạy vì mã đã weave gọi vào aspect class không?
- Bộ đóng gói có đặt class woven đúng nơi class loader thực tế tra cứu hay không?

Những câu hỏi này quan trọng hơn tên thư mục build: **chính tập bytecode mà JVM load quyết định chương trình có chạy advice hay không**.

## 6. Kiểm tra nhiều lớp: từ file đến hành vi

### 6.1. Kiểm tra cấu trúc tệp phát hành

| Lớp kiểm tra | Công cụ/kỹ thuật | Mục đích | Giới hạn |
|---|---|---|---|
| **File và đường dẫn** | `jar --list`, kiểm tra duplicate entries | Class/aspect/resource có được đưa vào đúng gói? | Có file chưa đồng nghĩa advice khớp |
| **Bytecode** | `javap -c -p`, trình đọc classfile | Có instruction hoặc helper do weaving tạo? Class version có đúng JDK đích? | Phải hiểu compiler-generated code |
| **Weave report** | `-showWeaveInfo`, diagnostics và cảnh báo build | Pointcut dự kiến đã tác động đúng kiểu/join point? | Log đúng chưa bảo đảm artifact cuối chứa đúng class |
| **Phụ thuộc** | Runtime classpath, dependency resolution, kiểm tra JAR | Lớp đã weave tìm được aspect và thư viện runtime? | Có thể bị nạp nhầm phiên bản |
| **Hành vi** | Smoke/integration tests chạy JAR cuối | Advice đúng thời điểm, đủ lượt, bảo toàn nghiệp vụ? | Một happy path không bao phủ mọi nhánh |
| **Triển khai** | Chạy bằng launcher/container/agent thật | Có cùng classpath, module path, loader và cấu hình trên môi trường đích? | Phải chọn workload đại diện |

Mỗi lớp kiểm tra trả lời một câu hỏi khác nhau. Một pipeline đạt chất lượng tối thiểu nên **kết hợp weave report, kiểm tra JAR cuối và kiểm thử hành vi**.

### 6.2. Kiểm tra bytecode và phiên bản Java

Lệnh sau in cả bytecode, metadata class và thông tin phiên bản khi cần:

```bash
javap -classpath build/calculator-woven.jar \
  -verbose demo.Calculator
```

Nếu target là Java 17, classfile tương ứng thường mang **major version 61**. Điều này xác nhận mức bytecode đầu ra, không khẳng định JAR chạy được trên mọi JVM Java 17: dependency, các API runtime và cấu hình module cũng phải phù hợp. Đừng giả định một compiler mới luôn mặc định target trùng Java 17; **chỉ định mức source/target rõ ràng**.

Khi weave thư viện Java có API nhạy cảm với binary compatibility, hãy kiểm tra tiếp:

- Method signature, visibility, generic signature và annotation mà client thực sự sử dụng.
- Serialization contract và `serialVersionUID` đối với lớp có thể serialize; việc weave có thể ảnh hưởng các chi tiết tương thích.
- Resource lookup, service loading, module descriptor, package sealing và class-loader boundary.
- Việc stack trace và line-number metadata còn đủ để debug sau weaving.

### 6.3. Kiểm thử advice phải bao phủ cả “chạy” và “không chạy”

Ngoài một trường hợp khớp, cần có trường hợp **không khớp pointcut**. Ví dụ một method khác không thuộc `Calculator.sum(int,int)` không được in dòng audit, nếu đó là hợp đồng cấu hình. Với một hệ thống có nhiều advice, kiểm tra:

1. **Số lần:** chính xác một lần mỗi join point mong muốn (hoặc số lần được định nghĩa rõ).
2. **Thứ tự:** `before`, `after returning`, `after throwing` và `around` theo semantics của cơ chế AOP đang dùng.
3. **Giá trị trả về/ngoại lệ:** advice không thay đổi vô ý result, exception, stack trace hoặc hành vi hủy.
4. **Đệ quy/self-call:** các lời gọi nội bộ thực sự là join point mục tiêu có bị advice áp dụng như dự định?
5. **Đa luồng:** advice có thread-safe khi ghi state/counter/context chung? Có tạo race condition?
6. **Biên giới lớp:** lớp được load bởi loader khác có dùng đúng woven class và phụ thuộc?
7. **Các trường hợp thiếu/không khớp runtime:** nếu loại bỏ phụ thuộc cần thiết thì build/runtime phải báo lỗi rõ ràng thay vì âm thầm bỏ advice.

Với logic quan trọng như bảo mật hoặc giao dịch, phải kiểm tra hành vi đầu-cuối; **chỉ thấy log của advice không thể thay thế kiểm thử kết quả nghiệp vụ**.

## 7. Đóng gói an toàn trong ứng dụng thực tế

### 7.1. JAR thường, executable JAR và dependency

Ví dụ đã tạo `calculator-woven.jar` là **JAR chứa class**, chạy bằng `java -cp ... demo.Main`. Lệnh `java -jar ...` chỉ hoạt động nếu JAR có manifest `Main-Class` phù hợp; hơn nữa khi dùng `-jar`, cơ chế classpath của launcher khác với truyền `-cp` ngoài lệnh. Nếu không xây gói tự chứa, cần cung cấp các JAR phụ thuộc bằng manifest `Class-Path` hoặc cơ chế chạy được kiểm chứng.

Khi tạo fat JAR, phải xử lý có chủ đích:

- Bản sao của `META-INF/services/*` và resource có tên trùng.
- Các manifest và metadata của dependency, chữ ký cryptographic không còn hợp lệ sau biến đổi/ghép.
- Thứ tự ghi khi có lớp trùng nhau; cần **fail build** nếu hai phiên bản class xung đột thay vì phụ thuộc thứ tự ngẫu nhiên.
- File license và thông tin phụ thuộc khi phân phối.
- Việc nạp `aspectjrt` hoặc runtime tương ứng trong chính môi trường sản xuất.

Hãy chạy smoke test trên **cùng kiểu đóng gói** sẽ xuất bản: nếu phát hành image/container thì kiểm tra bên trong image, không chỉ thư mục build.

### 7.2. Metadata, module và class loader

Weaving có thể sinh lời gọi tới lớp của aspect/helper. Nếu class loader đích không nhìn thấy các lớp đó, có thể phát sinh `NoClassDefFoundError` hoặc `LinkageError` ngay lần thực thi join point. Trong Java Platform Module System, module readability, exports/opens và module descriptor có thể ảnh hưởng khả năng liên kết hoặc reflection. Không dùng tùy chọn nới lỏng đóng gói một cách tự động khi chưa hiểu yêu cầu.

Đối với **multi-release JAR** (`META-INF/versions/*`), cần biết bản class nào áp dụng cho JDK triển khai. Weave sai biến thể hoặc chỉ kiểm tra base class có thể bỏ sót hành vi thực tế. Với **signed JAR**, quy trình hợp lệ thường là biến đổi → đóng gói → xác minh → ký artifact cuối, rồi xác nhận chữ ký trên chính artifact đó.

### 7.3. Không weave hai lần do pipeline lẫn lộn

Nếu vừa weave ở build vừa cấu hình transformer cùng loại lúc nạp lớp, ứng dụng có thể chịu kiểm tra thừa, weaving lại hoặc hành vi không lường trước theo khả năng reweaving của công cụ. Không giả định mọi class đã weave đều an toàn để biến đổi lần nữa. Ghi rõ **chủ sở hữu giai đoạn weaving**: build, post-compile hay runtime; test bằng cấu hình triển khai cuối.

### 7.4. Đầu vào không tin cậy và tính nguyên vẹn

Weaver xử lý bytecode do build cung cấp; binary dependency phải được quản lý với version và checksum đáng tin cậy. Khi phát hành:

- Chốt nguồn gốc và phiên bản của weaver/runtime; theo dõi thay đổi trong dependency graph.
- Ghi checksum cho artifact **sau weaving và packaging** (ví dụ SHA-256) để truy ngược đúng bản đã triển khai.
- Nếu yêu cầu build tái lập byte-for-byte, phải kiểm soát timestamp ZIP entries, thứ tự entries, manifest và input metadata; hai lần gọi `jar` thông thường không tự chứng minh đã tái lập hoàn toàn.
- Đừng sửa JAR đã ký hoặc đã phát hành mà vẫn giữ cùng danh tính/version như thể không thay đổi.

## 8. Kiểm tra CI/CD: quy tắc pass/fail có ý nghĩa

Ví dụ một pipeline tối thiểu:

```text
[1] Checkout + resolve toolchain có version cố định
[2] Clean output
[3] Compile & weave; lưu log, fail khi compiler lỗi
[4] Assert weave report có join point bắt buộc
[5] Package từ output woven, không từ input
[6] Inspect JAR: expected class/resource, không duplicate
[7] Chạy smoke test bằng JAR phát hành; so stdout/behavior
[8] Chạy unit/integration/regression với advice bật
[9] Chạy kiểm tra môi trường đóng gói cuối
[10] Tính checksum, ký (nếu cần), publish artifact đã kiểm tra
```

**Không chỉ dùng một tín hiệu:** build exit code có thể thành công dù pointcut không khớp; weave report có thể đúng nhưng bước package lấy nhầm bản chưa weave; JAR chứa đúng class nhưng runtime classpath lại chọn bản class khác.

Một ví dụ điều kiện fail chắc chắn trong smoke test đã nằm ở mục 4.5: `test "$actual" = "$expected"`. Trong ứng dụng lớn, nên thay so sánh stdout bằng assertion trên observable effect hoặc kết quả nghiệp vụ, với fixture kiểm soát được.

### 8.1. Kiểm thử phát hiện lỗi hồi quy pointcut

Khi đổi chữ ký phương thức, package hoặc modifier, pointcut tường minh có thể không còn khớp. Một số compiler có thể phát cảnh báo, nhưng **nếu không có yêu cầu về số join point bắt buộc thì pipeline vẫn có thể pass**. Quy ước hữu ích:

- Ánh xạ mỗi advice quan trọng tới một hoặc nhiều test chứng minh nó thực sự chạy.
- Lưu bản weave report để xem thay đổi join point giữa hai build, không coi chuỗi thông báo là API ổn định.
- Khi sửa pointcut, kiểm tra cả **phạm vi khớp thừa** vì aspect có thể chạm lớp không mong muốn, làm thay đổi hành vi và chi phí.
- Với aspect có quyền thay đổi dòng điều khiển (`around`), có test cho success, exception và path không gọi `proceed` nếu được thiết kế.

### 8.2. Ma trận chạy cần phù hợp sản phẩm

Chọn ma trận theo trường hợp có thật:

| Cấu hình | Cần quan sát |
|---|---|
| JDK đích thấp nhất được hỗ trợ | Class version, dependency và API dùng tại runtime |
| JDK môi trường production | Hành vi, module, class loader, JVM option |
| JAR phân phối | Woven class và runtime dependency có sẵn |
| Gói triển khai cuối (container, installer...) | Entry point, classpath, resource và smoke test thực |
| Có/nhiều Java agent khác | Transformer ordering, compatibility, không weave ngoài dự kiến |
| Đường lỗi/concurrent execution | Advice bảo toàn exception và thread safety |

Không cần nhân bản vô hạn mọi phép thử, nhưng ít nhất một bài kiểm tra phải chạy **artifact phát hành cuối cùng**, dưới cấu hình JVM gần production.

## 9. Khi artifact không hoạt động như mong đợi

| Hiện tượng | Chẩn đoán đầu tiên | Hướng khắc phục |
|---|---|---|
| Không có advice nhưng nghiệp vụ chạy | Weave report không khớp hoặc JAR lấy từ output plain | Kiểm tra pointcut và đường đóng gói; chạy đúng JAR cuối |
| Build báo weaving, runtime không có advice | JVM load bản `.class` ở classpath/module path khác | Xem loader/classpath, loại duplicate class, smoke test gói cuối |
| `NoClassDefFoundError` hoặc `LinkageError` | Thiếu aspect/helper/runtime hoặc loader không thấy chúng | Kiểm tra dependency, module và classpath thực |
| `UnsupportedClassVersionError` | Bytecode cao hơn JVM chạy | Chọn `-target` phù hợp và kiểm tra major version |
| `VerifyError` sau weaving | Bytecode transform không hợp lệ hoặc công cụ không tương thích | Kiểm tra JDK/weaver/agent, stack-map frame, biến đổi chồng chéo |
| Advice chạy hai lần | Khớp join point ngoài ý muốn hoặc dệt/chặn qua nhiều tầng | Phân tích weave report, call path và cấu hình weaving từng giai đoạn |
| JAR bị lỗi kiểm tra chữ ký | Bytecode/resource đổi sau bước ký | Weave và package trước khi ký lại tạo tác cuối |
| Test qua thư mục class pass nhưng triển khai fail | JAR thiếu resource, manifest, dependency hoặc class phù hợp | Test chính JAR/container được phát hành |
| Lỗi chỉ xuất hiện sau startup | Lớp được tải muộn, LTW thiếu transformer hoặc lazy configuration | Quan sát class loading/weave log trong luồng thực tế |

**Thứ tự debug hợp lý:** xác nhận JVM đang chạy *artifact nào* → artifact chứa *class nào* → class đã được weave *đúng join point nào* → runtime đang nhìn thấy *phụ thuộc và loader nào* → xác nhận *hành vi advice thực tế*. Nhảy thẳng sang suy đoán lỗi pointcut khi chưa xác nhận JAR được load rất dễ tốn thời gian.

## 10. Checklist nghiệm thu một tạo tác đã dệt

Trước khi xem artifact đủ điều kiện triển khai:

- [ ] Đã xác định rõ **CTW, binary weaving hay LTW**, cùng phạm vi join point cần áp dụng.
- [ ] Có đầu vào, weaver/compiler, JDK và dependency được cố định phiên bản.
- [ ] Output woven được tạo trong một nơi sạch và khác input chưa weave.
- [ ] Compiler/weaver thành công; báo cáo cho thấy **các join point bắt buộc** thực sự được dệt.
- [ ] JAR cuối chứa đúng class woven, aspect/helper, resource, manifest, module metadata cần thiết; không có class trùng gây chọn nhầm.
- [ ] Bytecode, classfile version, binary compatibility và phụ thuộc runtime đã được kiểm tra theo yêu cầu.
- [ ] Smoke test chạy từ **JAR/gói triển khai cuối**, kiểm tra cả advice và kết quả nghiệp vụ.
- [ ] Có test cho đường không khớp, ngoại lệ, thứ tự advice, nhiều luồng và call path đặc biệt nếu thuộc phạm vi chức năng.
- [ ] Cấu hình classpath/module path/agent/loader đã được kiểm tra trên JVM triển khai mục tiêu.
- [ ] Tạo tác đã xác minh được tính checksum và ký/phát hành đúng thứ tự khi cần.

## 11. Tài liệu kỹ thuật tham khảo

- [AspectJ — ajc compiler/weaver](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): các tùy chọn `-inpath`, `-aspectpath`, `-outjar`, `-showWeaveInfo` và cơ chế biên dịch/weaving.
- [AspectJ — Java version compatibility](https://github.com/eclipse-aspectj/aspectj/blob/master/docs/release/JavaVersionCompatibility.adoc): đối chiếu phiên bản công cụ với mức ngôn ngữ/bytecode Java.
- [Maven Central — org.aspectj:aspectjrt](https://central.sonatype.com/artifact/org.aspectj/aspectjrt/1.9.24): runtime cần cho bytecode đã weave bởi AspectJ trong ví dụ.
- [JDK tools — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) và [javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): đóng gói, liệt kê JAR, giải mã bytecode để kiểm tra.

**Kết luận kỹ thuật:** “đã weave thành công” là thuộc tính phải chứng minh trên **đầu ra thực sự được phát hành**, bằng đối chiếu **weave report + bytecode/JAR + runtime behavior**. Tách rõ input chưa weave với output đã weave và test trên artifact cuối sẽ loại bỏ phần lớn lỗi âm thầm trong quy trình tích hợp AOP.