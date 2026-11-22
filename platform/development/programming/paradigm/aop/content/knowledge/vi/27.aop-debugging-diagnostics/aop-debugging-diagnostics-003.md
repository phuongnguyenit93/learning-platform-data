# Đọc thông báo điểm đã được dệt và điểm không phù hợp trong AOP

## 1. Mục tiêu: đọc thông báo chẩn đoán thay vì đoán pointcut

Trong Aspect-Oriented Programming (AOP), một **pointcut** lựa chọn tập các *join point*, **advice** diễn tả hành vi muốn thực thi tại những điểm đó, còn **weaving** hoặc cơ chế chặn lời gọi khác biến ý định trên thành hành vi lúc chương trình chạy. Một vấn đề phổ biến khi gỡ lỗi là: source code đã chứa aspect, chương trình vẫn chạy, nhưng log/audit/metrics hay kiểm soát truy cập không xuất hiện tại phương thức mong muốn.

Muốn chẩn đoán chính xác, cần phân biệt **bốn lớp bằng chứng**:

1. **Aspect được nhận diện/đăng ký:** trình biên dịch hoặc weaver đã biết sự tồn tại của aspect.
2. **Một class được đưa qua weaver:** class ấy có được xem xét để biến đổi bytecode, nhưng chưa chắc có join point khớp.
3. **Một join point được dệt:** weaver đã áp một advice hoặc thay đổi liên quan vào vị trí bytecode cụ thể.
4. **Advice chạy thật tại runtime:** chương trình thực sự đi qua join point, các điều kiện động được thỏa, và cơ chế xử lý advice hoạt động.

Bốn trạng thái **không đồng nghĩa**. Một dòng `weaving 'MyClass'` có thể chỉ báo rằng weaver đang xử lý class, trong khi một dòng `weaveinfo Join point ...` cho thông tin cụ thể hơn về điểm cắt đã được dệt. Nhưng ngay cả thông báo có dệt ở build time cũng chưa chứng minh lần chạy hiện tại đã vào join point hoặc điều kiện động đã thỏa.

Bài này giải thích cách đọc thông báo **điểm đã dệt**, **điểm/advice không phù hợp**, cùng kỹ thuật chia nhỏ pointcut để tìm nguyên nhân. Ví dụ sử dụng công cụ AspectJ (`ajc`, `-showWeaveInfo`, `-Xlint`) để quan sát, nhưng các bước suy luận—kiểm tra phạm vi, join point, điều kiện, bytecode và hành vi—áp dụng cho AOP nói chung.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt thông báo compiler/weaver với kết quả thực thi advice.
- Đọc các tín hiệu `info`, `debug`, `weaveinfo`, `warning` và `error` trong đúng ngữ cảnh.
- Giải thích `adviceDidNotMatch` mà không suy diễn quá mức.
- Chẩn đoán pointcut sai loại join point, sai chữ ký, phạm vi weaving thiếu class hoặc đường gọi không qua điểm chặn.
- Phân biệt `call` và `execution` để biết classfile nào phải được dệt.
- Tái hiện có đối chứng bằng chương trình Java 17/AspectJ, log build, stdout và test âm tính.
- Thiết kế quy trình CI đánh giá *bằng chứng dệt* và *bằng chứng runtime* riêng biệt.

## 2. Từ source code tới advice chạy: sơ đồ nguyên nhân

~~~text
Khai báo aspect/pointcut
          |
          v
Compiler/weaver có nhận aspect không?
          |
          v
Classfile chứa join point có trong phạm vi weaving không?
          |
          v
Pointcut có khớp join point ở giai đoạn dệt không?
          |
          v
Advice có được dệt tại join point đó không?
          |
          v
Runtime có thực sự chạy qua join point đó không?
          |
          v
Các điều kiện động có đúng không?
          |
          v
Advice thực thi với kết quả/số lần/thứ tự mong đợi
~~~

Một bài gỡ lỗi hiệu quả không bắt đầu bằng việc thay bừa biểu thức pointcut. Hãy xác định **bước đầu tiên có bằng chứng thiếu**.

Ví dụ:

- Nếu không thấy aspect được đăng ký: xem cấu hình aspect, đường dẫn artifact và cách nạp.
- Nếu aspect có đăng ký nhưng class không được xem xét: xem include/exclude, classloader, build module, `inpath` hoặc agent.
- Nếu class được xem xét nhưng không có thông báo dệt mong đợi: xem loại join point, chữ ký và điều kiện pointcut.
- Nếu thấy dòng dệt nhưng runtime không có event: xem có đi qua đường gọi đó chưa, điều kiện động, thứ tự advice, exception và artifact đang chạy.
- Nếu advice chạy nhưng kết quả sai: xem hợp đồng của around/before/after advice, số lần `proceed`, retry, cleanup và biến đổi lỗi.

Cần luôn tách **bằng chứng compiler** ra khỏi **bằng chứng runtime**. Một pointcut có thể có điều kiện chỉ quyết định tại runtime; chỉ nhìn thông báo build chưa đủ.

## 3. Các nhóm thông báo và độ tin cậy của từng nhóm

| Tín hiệu | Nó chứng minh điều gì? | Nó **không** chứng minh điều gì? |
| --- | --- | --- |
| `info register aspect X` | Weaver nhận/đăng ký aspect X | X đã áp advice vào target cụ thể |
| `debug weaving 'Target'` | Weaver đang xử lý Target | Trong Target có advice match |
| `weaveinfo Join point '...' ...` | Một join point cụ thể nhận thao tác weaving/advice theo thông tin báo | Runtime đã đi qua điểm đó trong một request cụ thể |
| `warning adviceDidNotMatch` | Advice không match join point nào trong thế giới code mà đợt dệt biết/kiểm soát | Advice đó mãi mãi không thể match ở mọi deployment |
| `warning invalidAbsoluteTypeName` | Tên kiểu tuyệt đối trong pointcut không tìm thấy trong thế giới đã phân giải | Chắc chắn là bug nếu kiểu thuộc module chưa đưa vào build |
| `warning typeNotExposedToWeaver` | Có loại code cần cho weaving nhưng chưa được cung cấp cho weaver | Chỉ sửa pointcut sẽ chắc chắn giải quyết |
| `error` | Build hoặc weaving không thành công theo lỗi cụ thể | Artifact cũ trên classpath đã biến mất |

Các dòng ví dụ dùng **mẫu hình rút gọn**. Văn bản, mức log, số dòng, path, classloader và thông tin join point có thể khác giữa các phiên bản AspectJ hoặc phương thức compile/load-time weaving. **Không sao chép một log minh họa như log thực sự vừa chạy.**

### Ba nhầm lẫn cần tránh ngay

**Thấy “register aspect” rồi nghĩ advice đã hoạt động:** sai. Đây mới là bằng chứng đăng ký.

**Thấy “weaving class” rồi nghĩ tất cả method trong class được instrument:** sai. Weaver có thể xem xét class và không dệt advice nào.

**Thấy “weaveinfo” rồi nghĩ mọi lời gọi tới method đều đã được quan sát:** chưa đúng. Runtime phải đi qua bytecode đã weave, pointcut có thể có kiểm tra động, chương trình có thể chạy bản classfile khác và advice ngoài có thể short-circuit.

## 4. Bật thông tin chẩn đoán với công cụ minh họa AspectJ

### 4.1 Những tùy chọn chính

Đối với AspectJ compiler/weaver `ajc`, những tùy chọn hữu ích gồm:

- `-showWeaveInfo`: in thông báo về những join point nhận weaving. Đây là tín hiệu cụ thể nhất để kiểm tra một điểm đã được weave hay chưa.
- `-verbose`: phát thông tin xử lý/đăng ký ở mức rộng hơn.
- `-debug`: hữu ích trong bối cảnh thông báo debug của weaver, đặc biệt khi chẩn đoán load-time weaving; việc một class “được xem xét” không chứng minh advice đã dệt.
- `-Xlint` hoặc `-Xlint:warning`: phát các chẩn đoán về lỗi tiềm ẩn của crosscutting code.
- `-Xlint:error`: nâng mức mặc định của các nhóm lint lên error nếu phù hợp chính sách build.
- `-Xlintfile path/to/policy.properties`: định mức báo cho từng loại cảnh báo khi cần một policy chi tiết.
- `-log path/to/file`: lưu thông báo compiler vào file khi cần lưu bằng chứng build.

Tùy chọn nào hoạt động và cách cung cấp nó phụ thuộc compiler/weaver đang chạy; hãy kiểm tra phiên bản toolchain thực tế. Không dùng `-nowarn` hoặc tắt tất cả lint để “làm xanh build” khi điểm cắt bắt buộc đang mất match.

Một lệnh ví dụ ở môi trường đã cài `ajc`:

~~~bash
ajc -17 -showWeaveInfo -Xlint:warning \
    -classpath aspectjrt.jar \
    -d out WeaveMessagesDemo.java DiagnosticAspects.aj
~~~

Đây là **cú pháp bash nhiều dòng** bằng dấu `\`. Ở shell không hỗ trợ nối lệnh này, viết các tùy chọn trên một dòng. `-17` chỉ ra mức nguồn/bytecode Java 17 khi bản `ajc` hỗ trợ. `aspectjrt.jar` phải là đường dẫn tới runtime tương thích; nếu thư viện đã có trên classpath hệ thống, không cần lặp lại.

### 4.2 Khác biệt khi load-time weaving

Khi dùng **load-time weaving (LTW)**, log chẩn đoán liên quan **classloader cụ thể** và thời điểm class được định nghĩa. Tùy cấu hình, có thể bật các tùy chọn tương ứng trong cấu hình weaver hoặc system property như:

~~~text
aj.weaving.verbose=true
org.aspectj.weaver.showWeaveInfo=true
~~~

Đây là ví dụ **system properties** của AspectJ, không phải Java source hay cấu hình chung của mọi runtime. Trong môi trường thực tế, cần xác nhận weaver/agent đã hoạt động **trước khi** class đích được nạp. Nếu class đã load rồi, việc bật log sau đó không tự dệt lại class ấy theo mọi mô hình.

Một log hiển thị classloader không có nghĩa tất cả classloader trong ứng dụng cũng chịu cùng cấu hình. Mỗi loader có thể có danh sách include/exclude hoặc thời điểm khởi tạo khác nhau.

## 5. Ví dụ AspectJ hoàn chỉnh: một pointcut match, một pointcut không match

Chương trình nhỏ sau tạo ra ba loại bằng chứng:

1. Advice đầu khớp `execution(void Work.process(String))` và được dệt.
2. Advice thứ hai chọn `execution(void Work.ping(int))`, nhưng chương trình chỉ có `Work.ping()` không tham số; **không có join point tương ứng** trong đợt biên dịch.
3. Runtime thật gọi `process("A")` và `ping()`, nên chỉ advice thứ nhất in dòng “advice”.

**Tệp `WeaveMessagesDemo.java`:**

~~~java
public class WeaveMessagesDemo {
    public static void main(String[] args) {
        Work work = new Work();
        work.process("A");
        work.ping();
    }
}

class Work {
    void process(String value) {
        System.out.println("work=" + value);
    }

    void ping() {
        System.out.println("ping");
    }
}
~~~

**Tệp `DiagnosticAspects.aj`:**

~~~java
public aspect DiagnosticAspects {
    before(): execution(void Work.process(String)) {
        System.out.println("advice:process");
    }

    before(): execution(void Work.ping(int)) {
        System.out.println("advice:ping-int");
    }
}
~~~

**Lệnh biên dịch và chạy (Unix-like shell):**

~~~bash
mkdir -p out
ajc -17 -showWeaveInfo -Xlint:warning \
    -classpath aspectjrt.jar \
    -d out WeaveMessagesDemo.java DiagnosticAspects.aj
java -cp "out:aspectjrt.jar" WeaveMessagesDemo
~~~

Với Windows, ký tự phân cách classpath thường là dấu `;`, ví dụ `out;aspectjrt.jar`. Hai tệp cần nằm trong cùng thư mục làm việc hoặc truyền đường dẫn tương ứng.

**Stdout của chương trình khi build/weave thành công:**

~~~text
advice:process
work=A
ping
~~~

**Đọc log biên dịch:** `-showWeaveInfo` dự kiến đưa ra một thông báo dạng `weaveinfo Join point 'method-execution(void Work.process(java.lang.String))' ...` cho advice thứ nhất. Do advice thứ hai không có điểm khớp trong tập source này, lint `adviceDidNotMatch` có thể được phát ra. Cấu trúc đầy đủ của dòng, đường dẫn, thứ tự và mức cảnh báo còn phụ thuộc bản compiler và các tùy chọn lint, vì vậy **không tuyên bố nguyên văn stderr cố định**.

Dòng `advice:ping-int` **không thể xuất hiện** trong lần chạy bình thường được minh họa, vì không có method `Work.ping(int)`. Đây là lỗi chọn chữ ký, không phải bằng chứng mọi class đã bị bỏ ngoài phạm vi weaving.

### 5.1 Đối chứng khi build bằng javac thuần

Để xác minh sự khác nhau giữa bản có weaving và bản không weaving, biên dịch **chỉ Java** vào thư mục độc lập:

~~~bash
mkdir -p plain
javac -d plain WeaveMessagesDemo.java
java -cp plain WeaveMessagesDemo
~~~

**Stdout của bản plain:**

~~~text
work=A
ping
~~~

Không thể dùng `javac` để biên dịch cú pháp `aspect` trong tệp `.aj`. Khi chỉ build Java, classfile `Work` không được dệt bằng AspectJ; sự khác biệt stdout phản ánh chính điều này. Tuy nhiên, nếu chạy trên môi trường còn bật load-time weaving khác, cần tắt cơ chế đó khi thực hiện đối chứng plain.

### 5.2 Phép kiểm thử có mục đích sau khi sửa pointcut

Để khớp method `ping()` thật, sửa dòng chọn từ `Work.ping(int)` thành `Work.ping()`, sau đó build lại bản woven sạch. Lúc ấy advice tương ứng có thể được dệt, và stdout kỳ vọng thêm một dòng trước “ping”:

~~~text
advice:process
work=A
advice:ping-int
ping
~~~

Đây là **dự đoán nếu chỉ sửa pointcut** mà chưa đổi tên chuỗi in; chuỗi `advice:ping-int` vẫn giữ nguyên do literal trong thân advice. Trong code có ý nghĩa hơn, nên đổi nhãn thành `advice:ping` để tránh gây hiểu nhầm. Kết quả trên chỉ dùng để chứng minh **việc khớp chữ ký thay đổi khả năng dệt**, không liên quan giá trị của tên thông báo.

## 6. Đọc `adviceDidNotMatch` đúng nghĩa

`adviceDidNotMatch` là một loại lint điển hình được phát ra khi một advice **không có join point nào mà compiler/weaver xác định được là có thể bị ảnh hưởng** trong phạm vi đang được xử lý.

Nó thường gợi ý:

- Sai tên phương thức hoặc tên kiểu trong pointcut.
- Sai số lượng/kiểu tham số, sai modifier hoặc định dạng pattern.
- Pointcut chọn `call` trong khi phần code có `execution` khác kỳ vọng.
- Phạm vi `within`, `withincode`, annotation hoặc điều kiện ghép bị hạn chế quá mức.
- Class/JAR chứa vị trí cần dệt không nằm trong tập source/inpath được cung cấp.
- Tính năng aspect nằm trong thư viện dùng lại, còn target sẽ được weave **ở một bước hoặc ứng dụng khác**.

Điểm cuối đặc biệt quan trọng: nếu biên dịch một **thư viện aspect** mà chưa cung cấp mã ứng dụng sử dụng thư viện, thông báo “không match” có thể là **hợp lệ trong build thư viện**. Đừng coi một warning duy nhất là bằng chứng chính sách của hệ thống production đang sai, và cũng đừng mặc định bỏ qua mọi warning.

### 6.1 Ba cách hiểu sai cần tránh

**Sai:** “`adviceDidNotMatch` nghĩa là method đích không tồn tại trong mọi chương trình.”  
**Đúng:** Trong phạm vi mà đợt compile/weave hiện có thể thấy, advice không tìm thấy điểm phù hợp; method có thể tồn tại ở module/classloader khác hoặc trong build sau.

**Sai:** “Không có warning `adviceDidNotMatch` nghĩa là mọi lời gọi đều được instrument.”  
**Đúng:** Một advice khớp **ít nhất một** điểm không chứng minh nó khớp **tất cả** operation bắt buộc.

**Sai:** “Không có `weaveinfo` nghĩa là không có advice.”  
**Đúng:** Trước hết xác nhận đã bật `-showWeaveInfo` và đang đọc đúng output/log. Một số cơ chế chỉ xuất thông báo trong phạm vi build/loader của chúng; test runtime mới xác nhận hành vi thực.

### 6.2 Khi nào biến cảnh báo thành lỗi build?

Có thể cân nhắc **fail build** khi advice bắt buộc của một ứng dụng khép kín mất toàn bộ match, hoặc khi `typeNotExposedToWeaver` chỉ ra operation nhạy cảm nằm ngoài phạm vi weaving.

Không nên áp quy tắc “mọi lời cảnh báo adviceDidNotMatch đều fail” cho toàn bộ thư viện aspect dùng lại mà không có ngoại lệ có lý do. Chính sách CI nên có **allowlist có chủ sở hữu**, ghi rõ advice nào cố ý chưa match tại giai đoạn build và ở đâu sẽ được kiểm thử sau.

Nếu dùng `-Xlintfile` để điều chỉnh mức từng warning, không tắt nguyên một lớp cảnh báo một cách im lặng. Với authorization, audit bắt buộc hoặc transaction, cần một **coverage test** xác nhận toàn bộ operation thuộc diện bảo vệ; warning đơn lẻ không đủ thay thế test đó.

## 7. Những cảnh báo hữu ích khác

| Tên lint | Diễn giải thực hành | Hướng kiểm tra |
| --- | --- | --- |
| `invalidAbsoluteTypeName` | Tên kiểu tuyệt đối không tìm thấy hoặc không phân giải được | Kiểm tra package, classpath, import, relocation/rename, binary compat |
| `typeNotExposedToWeaver` | Kiểu có thể cần được dệt nhưng không được đưa vào phạm vi kiểm soát | Kiểm tra `inpath`, input JAR, module và classloader |
| `unmatchedSuperTypeInCall` | Kiểu khai báo trong `call` khác kiểu tĩnh của receiver ở vị trí gọi | Phân biệt compile-time receiver type với runtime target |
| `aspectExcludedByConfiguration` | Aspect bị loại khỏi cấu hình weaving, có thể do include/exclude | Kiểm tra bộ lọc cấu hình và phiên bản artifact |
| `adviceDidNotMatch` | Advice không tìm được join point tiềm năng | Thu nhỏ pointcut, kiểm tra đầu vào build, xác định ý đồ thư viện |

**Mức cảnh báo và tên bản ghi cần được xác thực theo phiên bản weaver.** Chúng là các tín hiệu chẩn đoán, không phải phép chứng minh đầy đủ của bảo mật hoặc tính đúng đắn.

Một lỗi `invalidAbsoluteTypeName` có thể xuất hiện vì package đã đổi sau refactor. Không nên “sửa” bằng cách thay mọi kiểu bằng `*` nếu điều đó làm pointcut trở nên quá rộng, chạm cả code hạ tầng hoặc dữ liệu nhạy cảm.

`unmatchedSuperTypeInCall` là gợi ý đặc biệt có giá trị: trong AspectJ, `call` thường bị ràng buộc bởi **kiểu tĩnh của biểu thức receiver tại call site**, không đơn giản bằng implementation class được gọi tại runtime. Nếu muốn match theo đối tượng runtime, hãy xem xét ràng buộc `target(Type)` theo semantics phù hợp, rồi kiểm chứng trên tập join point thực tế.

## 8. Gỡ lỗi pointcut theo phương pháp tách điều kiện

Một biểu thức pointcut lớn thường có dạng:

~~~text
P = kind && signature && lexicalScope && runtimeContext && exclusions
~~~

Nếu P không match, viết lại toàn bộ biểu thức theo cảm tính sẽ khó biết vấn đề ở đâu. Thay vào đó:

1. **Chọn đúng loại join point:** ví dụ `execution` thay vì `call` khi muốn dệt vào body method.
2. **Giới hạn phạm vi đơn giản:** lấy một lớp/phương thức chắc chắn nằm trong artifact đang weave.
3. **Thêm điều kiện chữ ký:** tên, return type, modifier và tham số; xác nhận method thật qua source/bytecode.
4. **Thêm điều kiện phạm vi lexical:** `within`/`withincode` theo vị trí code.
5. **Thêm điều kiện động:** `this`, `target`, `args`, `cflow` hoặc `if` khi có lý do.
6. **Thêm exclusions:** loại trừ các phương thức hoặc package không cần advice.
7. **Sau mỗi bước:** build sạch, đọc `weaveinfo`, so sánh danh sách join point, rồi test hành vi runtime.

Việc tách này giúp phân biệt **điều kiện tĩnh không match** với **điều kiện động chỉ được quyết định lúc thực thi**.

### 8.1 Ví dụ pointcut sai logic boolean

Không thể đồng thời là *method-call join point* và *method-execution join point* tại cùng một join point riêng lẻ:

~~~java
// Sai về ý nghĩa: không thể đồng thời là call và execution
call(* Work.*(..)) && execution(* Work.*(..))
~~~

Đây là **biểu thức AspectJ minh họa**, không phải chương trình độc lập. Nếu muốn chọn cả hai loại join point, hãy dùng:

~~~java
// Union của hai loại join point
call(* Work.*(..)) || execution(* Work.*(..))
~~~

Cẩn thận: chọn cả call và execution có thể làm **một thao tác nghiệp vụ** kích hoạt advice ở cả vị trí gọi lẫn thân method, dẫn đến đếm đôi nếu metric của bạn là request logic. Hãy xác định đơn vị quan sát trước khi đổi `&&` thành `||`.

### 8.2 `this`/`target` không có trong mọi ngữ cảnh

Ví dụ chọn `this(Work)` tại một điểm gọi từ method static có thể không match vì không tồn tại receiver “đang thực thi” tương ứng. Tương tự, `target(Work)` không phù hợp cho nhiều constructor-call join point trước khi đối tượng được tạo. Khi warning không match, cần xem loại join point và cách ràng buộc context, không chỉ kiểu tên class.

### 8.3 `args` là điều kiện theo vị trí

`args(String)` yêu cầu một danh sách tham số tương ứng với pattern của nó; nếu method có nhiều tham số, cần viết pattern phù hợp, ví dụ `args(String, ..)` khi muốn tham số đầu là String và cho phép các tham số sau. `args` kiểm tra điều kiện tại join point theo runtime semantics, không thay thế được kiểm tra số lượng và thứ tự tham số.

### 8.4 `within` khác `withincode`

- `within(TypePattern)` giới hạn theo vị trí lexical bên trong một kiểu.
- `withincode(SignaturePattern)` giới hạn theo vị trí lexical bên trong code của một member cụ thể.

Với `call` join point, vị trí lexical thuộc **caller**; với `execution`, vị trí lexical thuộc **body method được thực thi**. Vì vậy một pointcut `within(Work) && call(...)` có thể chỉ match các call site viết bên trong Work, chứ không match mọi lời gọi từ class bất kỳ vào Work.

Nếu muốn kiểm soát *execution* các method của Work, điểm bắt đầu nên là một `execution` pointcut có chữ ký rõ, không dùng `within` đơn độc rồi suy ra nó bắt mọi lời gọi.

## 9. Phân biệt `call` và `execution` khi đọc weaveinfo

### 9.1 `execution`: mã chứa thân method

`execution(void Work.process(String))` chọn thời điểm thực thi phần thân `process`. Để chèn execution advice, weaver phải có quyền xử lý **bytecode chứa method body** đó.

Một caller hoàn toàn không weave vẫn có thể gọi body của Work đã weave và kích hoạt execution advice. Đây là lý do thông báo `method-execution(...)` gắn với vị trí method body, không đòi hỏi mọi caller đều weave.

### 9.2 `call`: mã chứa vị trí gọi

`call(void Work.process(String))` chọn vị trí gọi, như dòng:

~~~java
work.process("A");
~~~

Nếu class chứa lời gọi đã weave, `call` advice có thể hiện diện tại đó, **dù class chứa body Work chưa weave**. Ngược lại, caller không weave thì `call` advice tại call site ấy không xuất hiện, kể cả body Work đã weave.

Vì vậy, trước một warning không match, cần trả lời:

- Pointcut chọn method **call** hay method **execution**?
- Code được đưa cho weaver gồm **caller** hay **target**?
- `-showWeaveInfo` đang hiển thị điểm ở phía nào?
- Tên kiểu/chữ ký tại call site là kiểu tĩnh nào? Có overload/generic bridge không?
- Có áp cùng advice ở call và execution gây đếm đôi hay không?

### 9.3 Direct call, self-invocation và proxy

Nếu hệ thống dùng JDK dynamic proxy, lời gọi `target.inner()` trực tiếp không đi qua proxy handler; lời gọi `target.outer()` rồi `this.inner()` trên target thường không tự vòng lại proxy. Nhưng với execution bytecode weaving tại `inner`, lời gọi nội bộ **vẫn có thể** nhận advice.

Do đó, không dùng log `weaveinfo` của bytecode weaving để kết luận một proxy đang chặn method, và cũng không dùng test self-invocation của proxy để kết luận bytecode weaving thất bại. Phải ghi rõ cơ chế và nơi điểm cắt thực sự được gắn.

## 10. Đọc một log chẩn đoán theo từng câu hỏi

Giả sử công cụ cho các nhóm thông báo sau (đây là **mô phỏng cấu trúc**, không phải bản chép log thực):

~~~text
INFO: aspect registered: AuditAspect
DEBUG: class Work presented to weaver
WEAVEINFO: method-execution(void Work.process(java.lang.String)) received advice
WARNING: adviceDidNotMatch for execution(void Work.ping(int))
~~~

Diễn giải chính xác:

1. Aspect được đăng ký, nên không cần bắt đầu bằng câu hỏi “có nhận aspect không?”.
2. Work đã được đưa qua weaver. Dòng này vẫn chưa chứng minh mọi method của Work nhận advice.
3. `process(String)` có một join point được dệt. Cần so sánh với danh mục điểm **phải** được dệt, không chỉ chấp nhận một match bất kỳ.
4. `ping(int)` là một điểm không phù hợp trong chương trình mẫu; cần kiểm tra chữ ký phương thức thật là `ping()`.
5. Cuối cùng chạy chương trình và xác nhận side effect advice, vì runtime có thể chạy bản artifact khác hoặc không đi qua điểm đã dệt.

Một dòng thông báo có thể chứa thêm **tên advice**, **aspect sở hữu advice**, **nguồn/vị trí dòng code** và **join point kind**. Khi điều tra, hãy lưu ít nhất những trường ấy để so sánh build.

## 11. Quy trình đọc log để khoanh vùng advice không khớp

Mục đích của bài này là biến **weave diagnostics** thành kết luận có kiểm chứng, thay vì lặp lại toàn bộ checklist cấu hình AOP. Lưu compiler/weaver version, tập class được xử lý, full pointcut và log gốc cùng phiên bản artifact.

1. **Aspect có xuất hiện trong log registration không?** Nếu không, chưa thể kết luận pointcut sai; xác minh aspect path/cấu hình trước.
2. **Có chứng cứ weaver xem xét đúng class hoặc call site không?** Với `execution` kiểm tra class chứa thân method; với `call` kiểm tra class chứa lệnh gọi. Thiếu input/weaving scope khác với không khớp chữ ký.
3. **Có `weaveinfo` cho đúng kind và chữ ký không?** So đủ declaring type, return type, tham số/overload, vị trí và advice ID; “weaving class” không bảo đảm method cần tìm nhận advice.
4. **Có `adviceDidNotMatch` hoặc lint type lookup không?** Xem phạm vi compiler đang xử lý và điều kiện động; cảnh báo không match trong một library build không tự chứng minh advice sẽ không match khi weave ứng dụng tiêu thụ.
5. **Tách từng điều kiện pointcut để kiểm tra giả thuyết.** Chọn join point kind và signature cụ thể trước, sau đó thêm `within`, `args`, `target`, `cflow` hoặc exclusions; so diff tập join point dự kiến với actual, không sửa bằng wildcard quá rộng.
6. **Kiểm tra runtime đối chứng.** Run artifact vừa weave, khẳng định một positive case được advice đúng số lần và một negative case không nhận advice; một dynamic predicate false có thể làm advice không chạy dù class đã được instrument.
7. **Chốt nguyên nhân hẹp nhất.** Ghi rõ “aspect chưa đăng ký”, “target ngoài scope”, “signature/kind sai”, “runtime condition false” hay “artifact chưa được chạy”; sửa đúng tầng rồi giữ log + regression test để so ở build sau.

**Mẫu báo cáo cần lưu:** `kind / expected signature / actual signature / aspect registration / class processing / weaveinfo or lint / runtime result / root cause`. Một warning đơn lẻ không đủ để chứng minh coverage; một weaveinfo đơn lẻ cũng không đảm bảo caller đã đi vào join point.

## 12. Đọc thông báo khi có điều kiện động

Không phải mọi điều kiện đều quyết định được tại build time. Pointcut chứa `this`, `target`, `args`, `cflow` hoặc `if` có thể cần kiểm tra dữ liệu runtime.

Ví dụ khái niệm:

~~~text
execution(* Work.process(..)) && target(Work) && runtimeCondition
~~~

Đây là **biểu thức mô tả**, `runtimeCondition` không phải pointcut designator độc lập có thể sao chép vào AspectJ. Ý nghĩa là: body Work.process được instrument tại nơi có thể match, nhưng điều kiện động có thể không đúng ở một lượt gọi cụ thể.

Một dòng weaveinfo có thể được phát ra vì weaver cài logic kiểm tra tại join point; **không đồng nghĩa mọi lượt chạy đều đi vào thân advice**. Khi test, phải chạy cả trường hợp điều kiện true và false, ghi event trước/sau tại runtime, và đảm bảo khi false không có side effect từ advice.

Trường hợp `cflow` đặc biệt dễ nhầm: compile-time weaving có thể chuẩn bị logic kiểm tra control flow, nhưng chỉ những lần thực thi nằm trong flow phù hợp mới nhận hành vi. Một test gọi target trực tiếp ngoài flow có thể không ghi event dù cùng method body đã được weave.

## 13. Một warning có thể hợp lệ, nhưng lỗ hổng coverage vẫn không được chấp nhận

Đối với **library aspect** dùng lại, một advice chưa match trong module library có thể là điều bình thường. Khi thư viện được áp cho ứng dụng thật, join point mới có thể xuất hiện. Cần một bài test tích hợp ở ứng dụng sử dụng thư viện để xác nhận số lượng và vị trí match.

Đối với **aspect bảo mật/audit bắt buộc**, “advice đã match ít nhất một điểm” lại không đủ. Giả sử các operation cần bảo vệ là:

~~~text
Required = {order.place, order.cancel, order.refund}
Matched  = {order.place, order.cancel}
Missing  = {order.refund}
~~~

Khi đó sẽ không nhất thiết có cảnh báo `adviceDidNotMatch`: advice đã match hai điểm. Nhưng operation `order.refund` bị bỏ sót, vi phạm chính sách. Vì vậy:

- Định nghĩa một **operation catalog** hoặc danh sách điểm bắt buộc.
- So sánh **Required** với **Matched**.
- Kiểm tra các đường thực thi gọi trực tiếp, job nền, callbacks và self-invocation.
- Áp dụng *default deny* hoặc bảo vệ bổ sung ở tầng tài nguyên khi chính sách yêu cầu.
- Xem cảnh báo lint như tín hiệu chẩn đoán, không thay thế phép chứng minh coverage.

Trong trường hợp chỉ dùng metrics tùy chọn, thiếu một điểm có thể làm mất quan sát chứ không thay đổi kết quả nghiệp vụ; vẫn cần tài liệu scope để dashboard không sai lệch âm thầm.

## 14. Dấu hiệu đáng ngờ khi sửa pointcut quá rộng

Một số cách “sửa nhanh” có thể che giấu bug:

- Thay `execution(void Work.process(String))` bằng `execution(* *(..))` để thấy nhiều weaveinfo: có thể instrument cả code hạ tầng, dẫn tới recursion và overhead.
- Thay `&&` bằng `||` tùy tiện: mở rộng tập join point ngoài dự kiến, thậm chí đếm cả call và execution.
- Bỏ mọi điều kiện `within`: advice có thể áp lên library hoặc method nhạy cảm mà không được kiểm soát.
- Tắt toàn bộ `-Xlint`: làm biến mất tín hiệu thiếu match mà không làm advice xuất hiện.
- Bỏ qua `typeNotExposedToWeaver`: khi target thực sự nằm ngoài build scope, pointcut đúng tên cũng không chèn được execution advice.
- Thêm ghi log trong advice và xem “thấy log” là đủ: advice có thể chạy hai lần, biến đổi exception hoặc bỏ qua original method.
- Chỉ đọc stdout của một demo đã weave rồi suy ra toàn bộ ứng dụng: module khác/classloader khác có thể không được xử lý.

Quy tắc sửa an toàn là: **dùng một điểm khớp hẹp, có thể chứng minh, rồi mở rộng có kiểm soát**. Ghi lại số join point trước/sau và test các vị trí không được chọn.

## 15. CI và tài liệu chẩn đoán có thể tái hiện

Một báo cáo điều tra nên có ít nhất:

~~~text
Aspect identifier: ...
Advice signature/pointcut: ...
Join point model: call / execution / ...
Expected operations: ...
Runtime entrypoints: ...
JDK + AspectJ compiler/weaver version: ...
Build mode: compile-time / post-compile / load-time weaving
Classpath / aspectpath / inpath / loader: ...
Weave diagnostics enabled: -showWeaveInfo, -Xlint:warning
Relevant weaveinfo: ...
Relevant lint messages: ...
Observed runtime advice invocations: ...
Observed original method invocations: ...
Matched but not required: ...
Required but not matched: ...
Fix and verification: ...
~~~

Đây là **mẫu báo cáo**, không phải kết quả đo của một ứng dụng cụ thể.

Ở CI, lưu compiler output và kiểm tra:

1. Có advice bắt buộc nào không được dệt?
2. Tập join point match có tăng/giảm bất thường sau refactor không?
3. Cảnh báo `adviceDidNotMatch` hoặc kiểu không được expose có ngoại lệ được duyệt không?
4. Tất cả operations quan trọng có test runtime qua entrypoint thật không?
5. Có kiểm thử negative/exclusion và bản build plain/woven đối chứng khi cần không?
6. Khi đổi toolchain hoặc classloader, danh mục join point đã được cập nhật/đối chiếu chưa?

Log weaving có thể lớn. Giữ đủ chi tiết cho điều tra nhưng tránh đẩy dữ liệu nhạy cảm từ advice vào log. Không đưa request body, access token, password hay ID định danh không cần thiết vào tên metric hay thông báo debug.

## 16. Những lỗi suy luận thường gặp

**“Có dòng weaving class thì advice chắc chắn đã dệt.”** Sai. Một class được weaver xử lý có thể không có join point match; cần xem `weaveinfo` cụ thể.

**“Có một dòng weaveinfo thì mọi phương thức trong class đều có advice.”** Sai. Weaveinfo nói về join point cụ thể, phải so với danh mục điểm cần bảo vệ.

**“Có warning adviceDidNotMatch nghĩa là chương trình chắc chắn bị lỗi.”** Không nhất thiết với aspect library hoặc thế giới code chưa hoàn chỉnh. Nhưng nếu đó là advice bắt buộc trong build application đầy đủ, cần điều tra.

**“Không có warning thì không thể bỏ sót join point.”** Sai. Advice có thể match một điểm nhưng bỏ sót nhiều operation khác.

**“Call và execution là cùng một vị trí.”** Sai. Call gắn với call site; execution gắn với method body. Phạm vi weaving có thể bao phủ một bên nhưng không bao phủ bên còn lại.

**“Runtime không thấy log nên compiler không weave.”** Chưa chắc. Có thể code không tới đó, điều kiện động false, chạy nhầm artifact, log collector chưa flush hoặc advice ngoài short-circuit.

**“Self-invocation luôn bỏ qua advice.”** Sai trong trường hợp body method đã được bytecode-weave cho execution advice. Kết luận bypass của một loại proxy không áp dụng cho mọi AOP.

**“Xóa một điều kiện pointcut khiến warning biến mất nghĩa là fix an toàn.”** Chưa chắc. Nó có thể tạo false positives, tăng overhead hoặc biến đổi hành vi của nhiều method không mong đợi.

## 17. Checklist thực hành

- [ ] Đã xác định cơ chế AOP: proxy, compile-time, post-compile hay load-time weaving.
- [ ] Đã biết loại join point: `call`, `execution` hay loại khác.
- [ ] Aspect thực sự được compiler/weaver nhận và không bị cấu hình loại trừ.
- [ ] Bytecode chứa join point thực sự nằm trong phạm vi weaving.
- [ ] Đã bật và đọc `-showWeaveInfo` cho build cần kiểm tra.
- [ ] Đã xem xét `-Xlint` và nguyên nhân của `adviceDidNotMatch` khi có.
- [ ] Đã kiểm tra `invalidAbsoluteTypeName`, `typeNotExposedToWeaver` và loại warning liên quan.
- [ ] Pointcut được tách thành loại điểm, chữ ký, lexical scope, dynamic context và exclusions.
- [ ] Có phân biệt điều kiện tĩnh với điều kiện chỉ đánh giá tại runtime.
- [ ] Có test advice chạy đúng số lần và original method đúng số lần.
- [ ] Có positive test, negative test và regression khi đổi tên/package/chữ ký.
- [ ] Có kiểm tra đường proxy/direct/self-invocation/job/callback khi áp dụng.
- [ ] Có bản woven/plain đối chứng hoặc bằng chứng artifact tương đương.
- [ ] Đã so sánh tập **bắt buộc** với tập **thực tế match**, không chỉ tìm một weaveinfo bất kỳ.
- [ ] Không tắt cảnh báo hoặc mở rộng wildcard chỉ để làm build xanh.
- [ ] Báo cáo cuối ghi rõ nguồn log, version toolchain, classpath và cách tái hiện.

## 18. Tài liệu tham khảo

- [AspectJ Problem Diagnosis Guide](https://eclipse.dev/aspectj/doc/latest/pdguide/pdguide.html) — thông báo compiler/weaver, `-showWeaveInfo`, lint và kỹ thuật phân rã pointcut.
- [AspectJ ajc Compiler/Weaver Guide](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html) — các tùy chọn `-showWeaveInfo`, `-Xlint`, `-Xlintfile`, build và classpath.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html) — mô hình join point, ý nghĩa pointcut và advice, giới hạn weaving.

## 19. Kết luận

**Đọc đúng thông báo weaving là đọc đúng mức bằng chứng.** Aspect đăng ký, class được đưa qua weaver, join point được dệt và advice chạy thật là bốn trạng thái cần kiểm tra riêng. `-showWeaveInfo` giúp xác nhận những điểm đã được dệt; `-Xlint` giúp phát hiện các trường hợp không match, sai kiểu hoặc không đủ phạm vi weaving; test runtime chứng minh chương trình thật đã đi qua advice và giữ đúng hợp đồng. Với AOP có tác động tới bảo mật hoặc tính toàn vẹn dữ liệu, cần thêm **so sánh tập operation bắt buộc với tập join point thực tế** để phát hiện cả những điểm bị bỏ sót mà không tạo một warning rõ ràng.