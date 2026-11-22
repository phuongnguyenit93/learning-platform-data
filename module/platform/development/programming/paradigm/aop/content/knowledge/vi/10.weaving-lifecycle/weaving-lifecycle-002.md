# Dệt sau biên dịch trên mã trung gian hoặc thư viện có sẵn

**Post-compile weaving (dệt sau biên dịch, binary weaving)** là kỹ thuật trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**: một bộ dệt (*weaver*) nhận **artifact đã được biên dịch**, xác định các **join point** mà **pointcut** lựa chọn, rồi tạo artifact mới có hành vi **advice** tại những điểm phù hợp. Với Java, đầu vào tiêu biểu là thư mục chứa tệp `.class` hoặc tệp thư viện `.jar`; các nền tảng khác có thể sử dụng mã trung gian (IL/IR) riêng.

Ý nghĩa “sau biên dịch” chỉ **thời điểm biến đổi artifact**. Nó **không** có nghĩa advice bắt buộc chạy sau thân nghiệp vụ: khi chương trình chạy, bộ weaver có thể đã bổ sung mã cho **before**, **after**, **around** hoặc loại advice tương ứng mà công cụ hỗ trợ.

Ưu điểm đáng chú ý là có thể dệt trên **thư viện đã tồn tại** mà không phải sửa từng tệp nguồn. Tuy nhiên, kỹ thuật này phải bảo đảm bytecode hợp lệ, hợp đồng phương thức không bị biến đổi trái ý, artifact được nạp đúng, và các quy tắc về chữ ký, quyền thay đổi thư viện, license và bảo mật được tuân thủ.

## 1. Phân biệt các thời điểm weaving

| Hình thức | Đầu vào | Thời điểm kết hợp advice | Lưu ý |
| --- | --- | --- | --- |
| **Compile-time weaving** | Nguồn chương trình/aspect và compiler được tích hợp | Trong quá trình biên dịch | Có thể sử dụng nhiều thông tin nguồn; cấu hình compiler là một phần build |
| **Post-compile weaving** | Class file, JAR hoặc biểu diễn đã biên dịch | Sau compiler, thường trước khi triển khai | Dùng binary có sẵn, không nhất thiết cần mã nguồn lớp đích |
| **Load-time weaving** | Class file lúc loader chuẩn bị định nghĩa lớp | Trong quá trình nạp lớp | Phụ thuộc agent/loader, cấu hình runtime và lớp có được nạp qua đường can thiệp hay không |
| **Proxy/wrapper runtime** | Đối tượng và lời gọi đi qua lớp đại diện | Khi tạo và sử dụng lớp bọc | Có thể không biến đổi binary của target; lời gọi bypass proxy thường không bị chặn |

Một post-compile pipeline khái niệm:

~~~text
Sources / precompiled library
             |
             v
      Compilation (if needed)
             |
             v
       UNWOVEN .class / .jar
             |
             +---------- Aspect definitions / compiled aspects
             |                       |
             v                       v
             [POST-COMPILE BINARY WEAVER]
                           |
                           v
                WOVEN .class / .jar
                           |
                           v
                Verify / test / publish
                           |
                           v
                JVM runs woven classes
~~~

Nếu thư viện bên thứ ba đã phát hành `payment-library.jar`, có thể bắt đầu ngay tại bước **unwoven JAR**, sau đó tạo **woven JAR** riêng. Dệt vào file binary **không đồng nghĩa** được phép phân phối lại hoặc chỉnh sửa thư viện bất kỳ; phải có quyền và tuân thủ license.

### 1.1 Weaving khác với advice execution

Trong build, weaver **thêm hoặc tổ chức mã**. Trong runtime, advice **được thực thi khi join point xảy ra**.

Ví dụ một advice `before` được dệt vào class hôm nay sẽ chạy **trước phương thức đích** mỗi khi phương thức đó được thực thi trong môi trường có tải bản class đã dệt. Việc dệt diễn ra từ trước không làm advice chạy một lần tại thời điểm build.

Không nhầm giữa:
- **Build event:** weaver phát hiện một execution join point.
- **Runtime event:** phương thức được gọi và advice thật sự chạy.
- **Telemetry event:** bản ghi mà advice gửi ra console/collector; không nhất thiết cùng số lần nếu có cache, retry, sampling hoặc lỗi.

## 2. Join point và pointcut sau biên dịch

Một class file không giữ toàn bộ nội dung văn bản nguồn. Do đó, pointcut của binary weaver phải dựa vào **dữ liệu nó có thể nhìn thấy** và quy tắc của mô hình AOP.

Các nguồn thông tin thường gồm:
- Class hierarchy, interface, tên lớp/phương thức và kiểu khai báo.
- JVM method/field **descriptor** đã được compiler tạo.
- Attributes có trong class file, ví dụ thông tin source line, generic signature hoặc annotation phù hợp.
- Các vị trí **call**, **execution**, field access hay điểm khác **nếu** mô hình cho phép.
- Một số điều kiện runtime về đối tượng và tham số, nếu weaver có thể tạo mã kiểm tra tương ứng.

Các khái niệm cần phân biệt:

**Join point** là loại điểm chương trình có thể can thiệp; **pointcut** chọn subset của những điểm đó. **Advice** là xử lý chạy ở điểm được chọn. **Weaving** đưa cách gọi/chạy advice vào biểu diễn thực thi. Không phải mọi instruction trong bytecode đều trở thành join point, và không phải mọi dạng join point đều được mọi bộ AOP hỗ trợ.

Ví dụ pointcut “chọn execution của `BillingService.pay`” khác pointcut “chọn call tới `pay`”:
- **Execution** liên quan đến việc thực thi phần thân được công cụ hỗ trợ.
- **Call** liên quan đến vị trí bên gọi phát sinh lời gọi; chữ ký/ngữ cảnh caller có thể khác execution.
- Nếu một công cụ chỉ chặn lời gọi qua proxy, không thể suy rằng nó đã sửa execution bytecode của mọi lớp.
- Nếu một công cụ chọn cả hai loại điểm, một thao tác có thể làm xuất hiện nhiều sự kiện can thiệp ở các vị trí khác nhau.

## 3. Mã trung gian sau compiler không giống hoàn toàn mã nguồn

### 3.1 Class file Java và JAR

Tệp `.class` theo đặc tả JVM gồm cấu trúc lớp, constant pool, phương thức, trường, descriptors, attributes và bytecode. Tệp `.jar` là gói lưu trữ thường chứa **nhiều class file và tài nguyên**. Khi binary weaver nhận JAR, nó phải quyết định những entries nào biến đổi và những entries nào bảo toàn.

Các khác biệt đáng chú ý:
- Comment/formatting nguồn không còn hữu dụng cho weaving trên class file.
- Tên biến cục bộ hoặc source-line có thể vắng nếu compiler không xuất thông tin debug.
- Annotation chỉ sẵn có theo retention và vị trí lưu metadata.
- **Generic type erasure** làm descriptor JVM khác cách đọc generic ở nguồn.
- Compiler có thể tạo **bridge/synthetic methods**, adapter hoặc cấu trúc phụ trợ khác.
- Lambda và các cấu trúc ngôn ngữ mới có biểu diễn đặc biệt, cần toolchain tương thích.

Vì vậy, một pointcut được mô tả bằng tham số generic `T` không tự bảo đảm có thể khớp trực tiếp với descriptor Java đã xóa kiểu.

### 3.2 Generic và bridge method

Ví dụ mảnh khai báo Java:

~~~java
interface Handler<T> {
    T handle(T value);
}

final class TextHandler implements Handler<String> {
    @Override
    public String handle(String value) {
        return value.toUpperCase();
    }
}
~~~

Đây là ví dụ khai báo **chưa phải chương trình độc lập có `main`**. Với generic `T` không ràng buộc, JVM có thể thấy descriptor hợp đồng dựa trên `Object` sau erasure. Compiler có thể sinh phương thức cầu nối (**bridge**) để bảo toàn dispatch từ giao diện tới `handle(String)`.

**Có bridge trong Reflection hoặc bytecode không có nghĩa mô hình AOP buộc phải coi bridge là một execution join point riêng.** Một số công cụ cố ý loại bridge/synthetic khỏi tập điểm cần weave, hoặc chuẩn hóa chúng theo nghiệp vụ. Vì vậy không kết luận một lời gọi sẽ kích hoạt hai advice chỉ dựa trên việc thấy hai method.

### 3.3 IR ở nền tảng khác

Một nền tảng dùng IL hoặc LLVM IR có metadata, kiểu, cách tối ưu và verifier riêng. Post-compile weaving ở đó vẫn mang nghĩa **biến đổi artifact trung gian sau một bước biên dịch**, nhưng không thể dùng công cụ `javap` hay quy tắc JVM descriptor để kết luận cho mọi hệ thống.

**Nguyên lý AOP** có tính tổng quát; công cụ và cấu trúc binary thì phụ thuộc nền tảng.

## 4. Các bước của binary weaver

Một pipeline có thể được phân tích thành các trách nhiệm sau:

1. **Nhận đầu vào**: class directory/JAR hoặc IR đã biên dịch, phiên bản compiler và artifact provenance.
2. **Phân tích kiểu**: classpath/module path, hierarchy, annotations, descriptors và metadata cần để so khớp.
3. **Tìm tập join point được hỗ trợ**: method execution, call, field access hoặc điểm khác trong mô hình.
4. **Đánh giá pointcut**: điều kiện chữ ký/cấu trúc và điều kiện runtime cần chèn mã kiểm tra.
5. **Tổng hợp advice**: đưa before/after/around, precedence, exception paths và helper vào chương trình.
6. **Phát ra artifact mới**: lớp đã biến đổi, tài nguyên và metadata đi kèm.
7. **Xác minh**: bytecode verifier, bài test nghiệp vụ, log weave, khả năng rollback và phân phối.

Các bước có thể được tối ưu hoặc kết hợp khác nhau, nhưng những trách nhiệm ấy là điều cần xem xét khi thiết kế pipeline.

~~~text
Read binary
    |
    v
Resolve hierarchy / signatures
    |
    v
Select supported join points
    |
    v
Match pointcuts
    |
    v
Compose advice and preserve control flow
    |
    v
Emit woven artifact
    |
    v
Verify bytecode + runtime behavior
~~~

Một weaver không đủ thông tin để giải quyết kiểu có thể bỏ sót pointcut hoặc báo lỗi. Vì thế **đúng classpath và dependencies** là yêu cầu quan trọng, không phải chỉ cần đưa file JAR đích vào công cụ.

## 5. Thực hành Java 17: trước và sau khi dệt

Để tránh nhầm lẫn về khả năng của JDK, phần này tách:
1. **Chương trình Java 17 thuần, chạy được bằng JDK**.
2. **Bước binary weaving bằng công cụ AOP bổ sung**. Đây là ví dụ minh họa một triển khai cụ thể; cú pháp và setup khác nhau với các weaver khác.

### 5.1 Tạo binary nghiệp vụ chưa dệt

Tạo file `LibraryService.java`:

~~~java
public final class LibraryService {
    public String greet(String name) {
        System.out.println("LIB greet=" + name);
        return "Hi " + name;
    }
}
~~~

Tạo file `DemoApp.java`:

~~~java
public final class DemoApp {
    public static void main(String[] args) {
        LibraryService service = new LibraryService();
        String result = service.greet("An");
        System.out.println("APP " + result);
    }
}
~~~

Trên shell kiểu POSIX:

~~~bash
mkdir -p original woven
javac --release 17 -d original LibraryService.java DemoApp.java
java -cp original DemoApp
~~~

Trên Windows PowerShell có thể tạo thư mục bằng `New-Item -ItemType Directory -Force original,woven`; phần còn lại dùng lệnh JDK. Lệnh `--release 17` yêu cầu compiler có hỗ trợ target Java 17.

Stdout của **bản gốc**:

~~~text
LIB greet=An
APP Hi An
~~~

Không có dòng advice vì chưa hề thực hiện weaving. Nếu muốn xem lớp đã biên dịch:

~~~bash
javap -classpath original -c LibraryService
~~~

Lệnh `javap -c` đọc bytecode từ class file; danh sách opcode chi tiết tùy compiler và không cần giống hệt giữa mọi JDK.

### 5.2 Định nghĩa aspect minh họa

Ví dụ công cụ cụ thể sau sử dụng **AspectJ `ajc`** – một bộ compiler/weaver hỗ trợ binary weaving. Đây là **một hiện thực AOP**, không phải cú pháp dùng chung cho mọi công cụ. Không cần sửa `LibraryService.java`.

Tạo file `TraceAspect.aj`:

~~~java
public aspect TraceAspect {
    before(): execution(String LibraryService.greet(String)) {
        System.out.println("AOP BEFORE");
    }

    after() returning: execution(String LibraryService.greet(String)) {
        System.out.println("AOP AFTER");
    }
}
~~~

Aspect chọn method **execution** `LibraryService.greet(String)`, in một dòng trước và một dòng khi return bình thường. Nếu phương thức ném ngoại lệ, `after() returning` không phải advice của nhánh lỗi.

### 5.3 Dệt trên thư mục class đã biên dịch

Cần có `ajc` phù hợp phiên bản Java 17 cùng thư viện runtime `aspectjrt.jar`. Chúng **không có sẵn trong JDK**. Giả sử đường dẫn runtime JAR đã được thiết lập trong biến môi trường `AJ_RT`, lệnh `ajc -version` chạy thành công và bộ công cụ hỗ trợ mức `-17`:

~~~bash
# Thiết lập AJ_RT theo nơi cài thực tế trước khi chạy.
ajc -17 -classpath "original:$AJ_RT"     -inpath original     -d woven     TraceAspect.aj

java -cp "woven:$AJ_RT" DemoApp
~~~

Trên Windows, dùng dấu `;` thay dấu `:` ở classpath và viết dòng lệnh theo cú pháp PowerShell. `-inpath original` là điều mấu chốt: bộ dệt nhận **.class đã có sẵn** thay vì biên dịch lại source nghiệp vụ. Output được phát riêng vào `woven`.

Stdout **kỳ vọng khi weaving thành công**:

~~~text
AOP BEFORE
LIB greet=An
AOP AFTER
APP Hi An
~~~

Hai dòng AOP là kết quả advice thực thi ở runtime. Hai dòng nghiệp vụ gốc giữ nguyên giá trị trong ví dụ. Các bước JDK thuần đã có stdout xác định; riêng đầu ra đã dệt là **kết quả được mô tả theo cấu hình `ajc` nêu trên**, không được xem là đã kiểm nghiệm ở máy khi chưa chạy bộ công cụ bổ sung.

### 5.4 Dệt từ JAR đã phát hành

Đóng gói binary gốc (bước JDK):

~~~bash
jar --create --file library-app-unwoven.jar -C original .
~~~

Sau đó đưa JAR vào cùng bộ weaver:

~~~bash
ajc -17 -classpath "original:$AJ_RT"     -inpath library-app-unwoven.jar     -outjar library-app-woven.jar     TraceAspect.aj

java -cp "library-app-woven.jar:$AJ_RT" DemoApp
~~~

`-inpath` nhận thư mục hoặc JAR, `-outjar` ghi một JAR mới. Tùy mô hình, có thể sử dụng **binary aspect** qua một đường aspect riêng thay vì cung cấp source aspect. Lệnh `-injars` đã lỗi thời trong tài liệu công cụ này, nên dùng `-inpath`.

**Không ghi đè JAR gốc** chỉ để “tiết kiệm tên file”. Giữ hai artifact riêng, biết chính xác bản nào đã weave, bản nào dùng để đối chiếu.

## 6. Khả năng làm việc với thư viện có sẵn và giới hạn

### 6.1 Điều có thể làm

- Dệt các join point thuộc phạm vi của thư viện **khi tool hỗ trợ và binary tương thích**.
- Áp dụng advice chung mà không sửa từng phương thức nghiệp vụ.
- Tạo bản thư viện mới cho môi trường cần logging/metrics/audit đặc biệt.
- Kiểm thử hành vi mới dựa trên class/JAR đầu vào được version hóa.
- Tổ chức step weaving trong CI/build pipeline để runtime tải artifact đã được kiểm chứng.

### 6.2 Điều không thể tự suy

- Không có source **không** nghĩa công cụ khôi phục được mọi tên tham số, generic metadata hoặc annotation ở cấp nguồn.
- Dệt vào file trên đĩa **không** khiến class đã nạp sẵn trong JVM đang chạy tự thay đổi.
- Mã do runtime sinh **sau pass dệt** không tự chịu post-compile weaving của pass đó.
- Dệt được một method execution **không** có nghĩa công cụ cũng dệt được mọi field access, native method hoặc constructor.
- Nếu thư viện dùng class loader riêng, cần xác minh runtime đang nạp **bản woven**, không phải bản gốc cùng tên.
- Tồn tại `Class.forName`, Reflection hoặc proxy trong ứng dụng không chứng minh binary weaver sẽ quan sát được mọi đường gọi ấy.
- Tool biến đổi được bytecode **không** chứng minh được phép đổi hoặc phát hành lại thư viện thương mại/bên thứ ba.

### 6.3 Binary weaving và proxy-based AOP

Với proxy, lời gọi trực tiếp tới target có thể bỏ qua lớp đại diện. Với weaving trực tiếp method execution trong lớp đã biên dịch, execution đó có thể được instrument tại lớp đích, nên đường gọi khác proxy **có thể** vẫn đi qua advice.

Nhưng phạm vi thật còn phụ thuộc vào **lớp nào đã được weave**, pointcut chọn execution hay call, và biến thể binary mà runtime nạp. Một phương thức ở thư viện chưa được weave sẽ không tự được instrument chỉ vì ứng dụng có một aspect được khai báo.

## 7. Hợp đồng phương thức sau khi dệt

Advice được thêm vào không chỉ ảnh hưởng log. Nó có thể tác động tới:

| Hạng mục | Nguy cơ nếu weaving/advice sai |
| --- | --- |
| Giá trị trả về | Around advice trả sai kiểu hoặc sửa kết quả không được phép |
| Ngoại lệ | Lỗi gốc bị nuốt, bọc sai hoặc bị lỗi log che mất |
| Tác dụng phụ | Gửi sự kiện, ghi dữ liệu hoặc transaction xảy ra quá nhiều/ít lần |
| Bảo mật | Advice kiểm tra quyền không bao phủ mọi đường vào, hoặc bị cache ngoài short-circuit |
| Tài nguyên | `finally`/cleanup không được bảo toàn trên mọi nhánh |
| Đồng thời | I/O trong advice gây contention, deadlock hoặc race condition |
| Hiệu năng | Instrument quá nhiều join point nóng gây overhead |
| Thông tin nhạy cảm | Advice ghi toàn bộ arguments/return values vào log |
| Tracing và audit | Hai công cụ cùng instrument tạo sự kiện trùng hoặc thiếu |
| Tương thích | Thay đổi binary làm thiếu phương thức/metadata mà bên gọi kỳ vọng |

Nếu một around advice có quyền không gọi continuation, các advice và phương thức nằm bên trong nó **có thể không chạy**. Cần kiểm tra thứ tự precedence khi nhiều aspect cùng chọn một join point. Thứ tự xử lý tệp lúc build **không thay thế** quy tắc precedence ở runtime.

### 7.1 Kiểm tra quyền ở vị trí không thể bị bỏ qua

Giả sử hai chuỗi advice được ghép khác nhau:

~~~text
Authorize(Cache(Business))
Cache(Authorize(Business))
~~~

Trong trường hợp thứ hai, một cache hit ở lớp ngoài có thể trả kết quả **trước khi** advice phân quyền bên trong chạy. Nếu mọi lần truy cập phải được bảo vệ, đây là lỗi nghiêm trọng. Không đủ chỉ nói “đã dệt Authorization vào chương trình”; phải chứng minh thứ tự và phạm vi can thiệp đúng với mọi nhánh.

### 7.2 Đo thời gian có phạm vi nào?

~~~text
Timing(Transaction(Business))
Transaction(Timing(Business))
~~~

Hai vị trí đặt timer có thể cho hai định nghĩa latency khác nhau. Nếu timer bao ngoài transaction, số đo có thể gồm phần xử lý giao dịch; nếu nằm bên trong, số đo hẹp hơn. Tên metric phải mô tả đúng phạm vi, không lấy thứ tự dệt làm một chi tiết vô hại.

## 8. Thứ tự nhiều phép biến đổi

Một ứng dụng có thể dùng:
- Bộ dệt AOP.
- Bộ biến đổi bytecode để tracing/profiling.
- Công cụ coverage.
- Công cụ obfuscation.
- Bộ tạo mã hoặc bộ tối ưu hóa.

Khi đó, thứ tự xử lý ảnh hưởng **artifact nào được nhìn thấy bởi bước tiếp theo**.

~~~text
javac → generated bytecode → AOP weaver
      → coverage/profiler transform → packaging
~~~

Nếu obfuscator đổi tên phương thức trước khi pointcut theo tên được áp dụng, pointcut ấy có thể không còn khớp như lúc đọc source. Nếu một bộ transform tạo helper mới trước weaving, helper ấy **có thể** trở thành một ứng viên join point khi công cụ có hỗ trợ, nhưng không được mặc định mọi helper đều được weave.

Từ góc độ mô hình, với hai phép biến đổi `W` và `O`:

~~~text
W(O(P)) có thể khác O(W(P))
~~~

Chúng **không nhất thiết giao hoán**. Thứ tự biến đổi cũng không đồng nhất với thứ tự `before`/`after` giữa các advice sau khi chương trình chạy. Phải xác định thứ tự pipeline và precedence một cách độc lập.

### 8.1 Dệt lặp (reweaving) và idempotency

Nếu đầu ra của một pass weaving lại trở thành đầu vào của pass tiếp theo, không được mặc định:

~~~text
W(W(P)) == W(P)
~~~

Một số công cụ hỗ trợ reweaving bằng metadata hoặc giao thức riêng; một số có thể tạo mã chèn lặp hoặc báo lỗi. Không khẳng định “dệt hai lần chắc chắn chạy advice hai lần” cho mọi công cụ, nhưng phải kiểm chứng trước khi cho phép pipeline làm vậy.

### 8.2 Incremental build

Thay aspect hoặc pointcut có thể tác động nhiều lớp đã dệt, dù nguồn của lớp nghiệp vụ không đổi. Một build cache cần xét **hash input artifact, phiên bản aspect, weaver, pointcut và cấu hình** để tái tạo đúng các lớp chịu ảnh hưởng.

Nếu clean build và incremental build không tương đương về **join point được chọn và hành vi**, cần kiểm tra invalidation, classpath, nguồn input của pass sau và artifact woven cũ bị dùng lại.

## 9. Tương thích bytecode và JVM

Một weaver sửa class file phải tạo kết quả hợp lệ theo JVM verifier và runtime mục tiêu:

- Bytecode đúng kiểu toán hạng và thứ tự stack.
- Control flow hợp lệ ở nhánh thành công và lỗi.
- `try/catch/finally` và các bảng exception được cập nhật đúng.
- Stack-map frames/attributes phù hợp phiên bản class file nơi cần thiết.
- Method descriptor, visibility và interface contract không bị phá.
- Metadata cần cho Reflection/serialization hoặc các công cụ khác được xử lý có chủ đích.
- Runtime dependencies của advice hiện diện trên classpath hoặc module path.

Nếu không, chương trình có thể bị `VerifyError`, `ClassFormatError`, `NoSuchMethodError`, `IllegalAccessError` hoặc lỗi runtime khác dù tệp JAR đã được ghi thành công.

Đừng xem việc chèn vài opcode thủ công vào class file mà không hiểu **stack frames, constant pool và verifier** là kỹ thuật production an toàn. Nên dùng bộ weaver tương thích với phiên bản class file hiện tại và kiểm thử trên JVM thực sự sẽ triển khai.

## 10. JAR đã ký, giấy phép và nguồn gốc artifact

**Dệt vào thư viện có sẵn là thay đổi nội dung binary.** Một JAR đã có chữ ký số hoặc digest có thể không còn xác minh đúng sau khi class file bị sửa.

Quy trình tốt:

1. Xác minh **quyền thay đổi/phân phối** theo license và chính sách tổ chức.
2. Lưu artifact **chưa dệt** cùng thông tin phiên bản và hash.
3. Tạo bản **đã dệt** ở tên/đường dẫn khác, có build record rõ ràng.
4. Kiểm tra metadata chữ ký/digest. Nếu quy trình yêu cầu ký artifact, **ký mới bằng quy trình được ủy quyền**, không giữ nhãn gây hiểu nhầm rằng bản đã sửa vẫn là file nguyên gốc.
5. Ghi lại phiên bản compiler, JDK, weaver, aspect, classpath và cấu hình pointcut.
6. Duy trì artifact provenance/SBOM, quét lỗ hổng và kế hoạch rollback khi áp dụng.
7. Kiểm tra thư viện được phân phối đến runtime thực sự là bản woven đã được xác minh.

Một JAR còn có manifest, service provider metadata, tài nguyên, multi-release entries và có thể các tệp ngoài class file. **Không được chỉ kiểm tra vài class rồi mặc định toàn bộ JAR đã được bảo toàn**.

### 10.1 Multi-release JAR

Một multi-release JAR có thể chứa các biến thể class cho nhiều phiên bản Java. Nếu weaver chỉ biến đổi class ở đường cơ bản nhưng runtime thực tế chọn entry `META-INF/versions/17`, advice mong đợi có thể không chạy. Cần xác minh công cụ hiểu cấu trúc JAR này và những class **runtime thực sự chọn** đã được biến đổi đúng.

### 10.2 Module system và class loader

Binary weaving không tự cấp quyền reflective access hoặc mở các module không cho truy cập. Nếu aspect cần truy cập member không công khai hoặc metadata nội bộ, phải xem quy tắc visibility, module boundaries và công cụ weaving hỗ trợ những gì.

Hai lớp cùng tên được load bởi các class loader khác nhau có thể là những runtime types khác nhau. Không thể bảo đảm advice được áp dụng chỉ vì nhìn thấy đúng tên class trong thư mục build.

## 11. Kiểm thử trước khi phát hành

Một test suite nên kiểm chứng **cấu trúc lẫn hành vi**.

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Bản chưa dệt | Kết quả nghiệp vụ baseline và ngoại lệ gốc |
| Bản đã dệt | Advice chỉ xuất hiện ở join point được chọn |
| Lời gọi thành công | Giá trị trả về và tác dụng phụ theo hợp đồng |
| Lời gọi ném lỗi | Exception propagation và cleanup không đổi trái ý |
| Many-advice precedence | Đúng thứ tự vào/ra, không short-circuit lớp bắt buộc |
| Direct calls, proxies, self-calls | Biết đường nào được weaver bao phủ |
| Generic/bridge/synthetic | Không đếm trùng hoặc bỏ sót do chữ ký khác |
| Tải từ JAR | Runtime chọn woven artifact, không phải bản gốc |
| Chạy nhiều luồng | Không sinh race, deadlock, contention không chấp nhận |
| Metrics/logging | Không in args, response hoặc thông tin nhạy cảm tùy tiện |
| Trước/sau obfuscation | Pointcut match đúng trên biểu diễn thực tế |
| Clean vs incremental | Kết quả weaving và hành vi tương đương |
| JAR metadata/signature | Các tài nguyên, manifest và tính toàn vẹn được quản lý |
| Performance | Overhead đo được và đáp ứng ngân sách |

Trong ví dụ Java 17, có thể kiểm tra artifact woven:

~~~bash
jar --list --file library-app-woven.jar
javap -classpath library-app-woven.jar -p -c LibraryService
java -cp "library-app-woven.jar:$AJ_RT" DemoApp
~~~

Các lệnh giúp thấy danh sách file, bytecode và output runtime, nhưng **không có một lệnh đơn lẻ đủ để chứng minh toàn bộ ngữ nghĩa AOP đúng**. Nếu classpath còn thư viện khác, cần bổ sung đầy đủ các dependency và dùng phép thử tích hợp thực.

## 12. Những sai lầm thường gặp

1. **“Post-compile nghĩa advice chạy sau method.”** Không: đây là thời điểm dệt, không phải loại advice.
2. **“Phải có source code của lớp đích.”** Binary weaving có thể dùng class/JAR đã biên dịch.
3. **“JDK tự weave aspect khi chạy javac.”** Không: ví dụ dùng riêng `ajc`; `javac` chỉ tạo bản gốc.
4. **“Mọi method trong Reflection đều có execution join point.”** Không: mô hình AOP có giới hạn.
5. **“Bridge tồn tại tức sẽ có hai lần advice.”** Không suy được chỉ từ danh sách phương thức.
6. **“Dệt JAR rồi có thể tiếp tục dùng chữ ký số cũ như chưa sửa.”** Không: nội dung đã biến đổi cần kiểm tra integrity/ký lại được ủy quyền.
7. **“Dệt lên file dependency trong cache là tiện nhất.”** Sai: dễ gây mất provenance và làm bẩn build input.
8. **“Chỉ cần output JAR tồn tại là hoàn thành.”** Chưa đủ; cần verifier/linkage, pointcut và business tests.
9. **“Runtime chắc chắn nạp JAR woven vì tên file gần giống.”** Chưa đủ; kiểm tra classpath/class loader thực tế.
10. **“Cứ dệt lại để chắc chắn, không sao.”** Phải hiểu reweaving/idempotency.
11. **“Binary weaver luôn có mọi thông tin nguồn.”** Không: metadata có thể thiếu hoặc bị obfuscate.
12. **“Weaver postcompile nhìn thấy code runtime mới sinh sau build.”** Không trong một pass đã kết thúc.
13. **“Đổi thứ tự các bytecode tools không ảnh hưởng kết quả.”** Có thể ảnh hưởng signatures, pointcut và mã được chèn.
14. **“License không liên quan nếu chỉ sửa bytecode.”** Sai: quyền sửa/phân phối thư viện cần được tôn trọng.

## 13. Checklist triển khai

- [ ] Xác định bản **unwoven** làm đầu vào và lưu riêng.
- [ ] Kiểm tra license/quyền sửa binary, class/JAR format và compiler target.
- [ ] Chọn bộ weaver tương thích phiên bản JVM và đúng loại join point.
- [ ] Xác nhận **inpath**, classpath/module path, runtime library và aspect definitions.
- [ ] Hiểu pointcut match static signatures, generic erasure, bridge và mã sinh thế nào.
- [ ] Hạn chế phạm vi advice và quản lý precedence.
- [ ] Xác minh các công cụ obfuscation, coverage, tracing và weaving không xung đột.
- [ ] Xây **woven artifact riêng**, không ghi đè dependency nguyên gốc.
- [ ] Kiểm tra metadata, chữ ký số, multi-release JAR và service files.
- [ ] Chạy lại business tests, nhánh lỗi, cleanup, bảo mật, hiệu năng.
- [ ] Kiểm tra runtime dùng bản woven, không phải class chưa dệt ở nơi khác.
- [ ] Có build provenance, clean/incremental comparison và rollback.

## 14. Câu hỏi tự luyện

**Câu 1.** Có một JAR chỉ chứa compiled classes, không có source trong môi trường build. Có thể dùng post-compile AOP không?

**Đáp:** có thể nếu bộ weaver hỗ trợ bytecode ấy, có classpath đủ, có quyền thay đổi/phân phối và pointcut match join point được hỗ trợ. Không bảo đảm mọi loại thao tác đều weave được.

**Câu 2.** Advice `before` đã được dệt vào method execution. Nó chạy lúc biên dịch hay lúc method được thực thi?

**Đáp:** việc **đưa mã advice vào artifact** xảy ra ở bước dệt; hành vi before thực sự **chạy lúc join point xảy ra** trong JVM nạp bản đã dệt.

**Câu 3.** Tại sao thêm advice vào thư viện đã biên dịch có thể thất bại dù bytecode tồn tại?

**Đáp:** không tương thích phiên bản class file, thiếu type/dependency, pointcut không match, loại join point không hỗ trợ, metadata/annotation cần thiết thiếu hoặc code được load từ bản khác.

**Câu 4.** Chỉ thay JAR trên đĩa khi JVM đang chạy có làm class đã nạp dùng bytecode mới ngay không?

**Đáp:** không. Cần cơ chế triển khai/nạp lại hoặc cơ chế cập nhật runtime được hỗ trợ, không thể suy từ thao tác thay file.

**Câu 5.** Vì sao cần giữ cả artifact trước và sau weaving?

**Đáp:** để đối chiếu join points, kiểm chứng bytecode, hỗ trợ rollback, phân biệt bug weaving với bug nghiệp vụ và kiểm soát artifact provenance.

**Câu 6.** Nếu pointcut dựa vào tên phương thức nguồn mà obfuscator đổi tên trước khi weave, điều gì có thể xảy ra?

**Đáp:** pointcut có thể không còn khớp; cần hiểu thứ tự biến đổi, metadata và mapping của toolchain.

**Câu 7.** Vì sao không nên log toàn bộ `args` trong advice mới dệt vào thư viện bên thứ ba?

**Đáp:** có thể chứa password, token hoặc dữ liệu cá nhân và phát tán tới các hệ thống log; cần allowlist, data minimization và kiểm thử bằng dữ liệu giả.

## 15. Tham khảo

- [AspectJ — Load-Time Weaving Guide](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): phân biệt các thời điểm compile-time, post-compile và load-time weaving.
- [AspectJ — ajc Compiler/Weaver](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): công cụ minh họa binary weaving `-inpath`, `-aspectpath`, `-d`, `-outjar`.
- [JVM Specification, Java 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): cấu trúc class file.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra bytecode và method descriptors.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): cấu trúc, chữ ký và multi-release JAR.

**Kết luận:** Post-compile weaving cho phép **dệt vào mã trung gian hoặc thư viện đã biên dịch**, tạo artifact mới có advice tại các join point được hỗ trợ mà không bắt buộc sửa mã nguồn nghiệp vụ. Độ chính xác của kỹ thuật phụ thuộc vào **cấu trúc binary, classpath, pointcut, khả năng weaver, thứ tự biến đổi và artifact mà runtime nạp**. Hãy kiểm chứng bằng bytecode inspection, business tests và quy trình phát hành tin cậy; không đánh đồng khả năng sửa binary với sự an toàn hay quyền được phân phối binary đã sửa.
