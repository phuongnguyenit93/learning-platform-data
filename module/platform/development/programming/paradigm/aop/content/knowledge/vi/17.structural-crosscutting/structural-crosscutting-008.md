# Tương thích mã nguồn, tương thích nhị phân và chi phí bảo trì

## 1. Vì sao thay đổi cấu trúc bằng aspect là vấn đề tương thích?

Trong **Aspect-Oriented Programming (AOP)**, pointcut chọn *join point* còn advice bổ sung hành vi khi điểm ấy xảy ra. Một số mô hình AOP còn hỗ trợ **cắt ngang cấu trúc (structural crosscutting)** bằng *introduction/inter-type declaration*: một nhóm type có thể nhận thêm interface, method, field hoặc quan hệ khai báo. Điều này giúp tránh sửa lặp lại nhiều class, nhưng đồng thời làm thay đổi **hợp đồng mà mã nguồn, bytecode, trình liên kết, reflection và các module phụ thuộc nhìn thấy**.

Ví dụ, một introduction áp dụng cho `Order`, `Invoice` và `Shipment`:

~~~text
TRƯỚC:
  Order                 Invoice               Shipment
  (không có Trackable)   (không có Trackable)   (không có Trackable)

STRUCTURAL ASPECT, nếu công cụ hỗ trợ:
  introduce Trackable
  introduce trackingId(): String

SAU KHI WEAVE ĐÚNG:
  Order implements Trackable
  Invoice implements Trackable
  Shipment implements Trackable
~~~

Các dòng mô tả trên là **pseudocode khái niệm**, không phải một cú pháp được mọi công cụ AOP hỗ trợ. Nếu cơ chế chỉ tạo **wrapper/proxy triển khai interface mới** thì class gốc không tự thay đổi. Đó là một đối tượng proxy có contract rộng hơn, khác với introduction dệt trực tiếp vào class.

Khi phát hành thay đổi, phải trả lời bốn câu hỏi độc lập:

1. **Tương thích mã nguồn (source compatibility):** client source cũ có biên dịch lại được với API mới mà không sửa không?
2. **Tương thích nhị phân (binary compatibility):** client `.class` cũ có tiếp tục liên kết và gọi được API mới không?
3. **Tương thích hành vi (semantic compatibility):** result, exceptions, side effects, method selection và pointcut/advice order có giữ hợp đồng không?
4. **Tương thích công cụ và vận hành:** đúng woven artifact, classloader, compiler, reflection, serializer và lifecycle triển khai không?

Một bản cập nhật có thể **source-compatible, binary-compatible nhưng vẫn behavior-breaking**. Một thay đổi khác có thể **source-breaking và binary-breaking**. Vì vậy “build xanh” hoặc “không sửa source” chưa đủ kết luận an toàn.

## 2. Behavioral crosscutting khác structural crosscutting

**Behavioral crosscutting** bổ sung hành vi tại một join point:

~~~text
BEFORE execution(pay): ghi trace
AROUND execution(pay): authorize -> proceed -> metrics
AFTER THROWING: quan sát ngoại lệ
~~~

Đó là mã mô tả ý niệm. Cơ chế thực có thể dùng proxy hoặc bytecode weaving. Một behavioral weaver sửa instructions bên trong classfile nhưng **không nhất thiết bổ sung public API/member**.

**Structural crosscutting** biểu đạt sự thay đổi về kiểu hoặc khai báo:

~~~text
INTRODUCE interface Trackable vào những type được chọn
INTRODUCE method trackingId() với signature và implementation
~~~

Điểm phân biệt không phải “file `.class` có bị sửa hay không”. Cả hai kiểu can thiệp có thể sửa bytecode. Điểm phân biệt là **hợp đồng thực thi tại join point** hay **hình dạng/quan hệ của type**.

Một advice có field đếm `invocations` nằm trên object advice không có nghĩa target class nhận một introduced field. Một dynamic proxy triển khai `Tagged` cũng không biến raw target thành `Tagged`; cần kiểm **đúng object**.

## 3. Bảng khái niệm compatibility

| Cấp độ | Điều phải kiểm | Dạng lỗi hoặc thay đổi |
| --- | --- | --- |
| Source | Client source cũ compile lại với library/aspect mới | `cannot find symbol`, ambiguous overload |
| Binary | Client `.class` cũ resolve owner/method/field descriptors | `NoSuchMethodError`, `NoSuchFieldError` |
| Type/linkage | Runtime kind, hierarchy, access, loaders phù hợp | `IncompatibleClassChangeError`, `IllegalAccessError`, `ClassCastException` |
| Semantic | Caller nhận đúng value/exception, target đúng số lần | Overload khác, advice retry, result transformation |
| Reflection | Methods, fields, interface set, annotations đúng | Serializer/ORM khám phá property mới |
| Serialization | Dữ liệu cũ/mới tương tác theo contract | Schema drift, `serialVersionUID` |
| Build | Compiler/weaver/IDE nhất quán | Compile với woven, chạy với raw |
| Deployment | Runtime nạp đúng version và defining classloader | Bản JAR khác, agent cài muộn |

Tính tương thích luôn được phát biểu **so với client nào và trong ngữ cảnh nào**. “Version mới tương thích” là phát biểu thiếu thông tin nếu không nói đang giữ mã nguồn, binary, dữ liệu hay hành vi.

## 4. Source compatibility: cùng nguồn có còn biên dịch được?

Xét một thư viện v1:

~~~java
public final class PublicApi {
    public String id() { return "id-v1"; }
    public String render(Object input) { return "Object-v1"; }
}
~~~

Client:

~~~java
PublicApi api = new PublicApi();
api.id();
api.render(null);
~~~

Ở v1, `render(null)` chọn `render(Object)` vì chỉ có overload đó. V2 thêm:

~~~java
public String render(String input) {
    return "String-v2";
}
~~~

Khi biên dịch **cùng source client** với v2, compiler biết `String` cụ thể hơn `Object` và có thể chọn `render(String)`. Client không phải sửa source, nhưng đường thực thi và kết quả thay đổi.

**Source compatibility không hứa giữ nguyên overload binding và semantics sau recompilation.** Nếu hai overload không có một lựa chọn cụ thể hơn rõ ràng — chẳng hạn `render(String)` và `render(Integer)` với một lời gọi `null` phù hợp cả hai — có thể xuất hiện ambiguity.

Introduction thêm method hàng loạt vào nhiều classes có thể gây cùng hiện tượng này mà developer chưa hề sửa những call sites.

### 4.1. Thêm interface không luôn vô hại

Nếu một structural aspect giới thiệu interface có abstract methods cho nhiều classes, một compiler xử lý contract đó phải đảm bảo implementation phù hợp. Nếu thêm default methods vào các interfaces khác nhau mà chúng xung đột, một type có thể cần cách resolution rõ ràng. Giới thiệu một method trùng erasure của generic method cũng có thể tạo name clash.

Không áp quy tắc máy móc “cứ thêm là source-compatible”. Luôn test **client source** và **implementors** thực tế.

## 5. Binary compatibility: cùng `.class` có liên kết được không?

Khi biên dịch Java, client tạo symbolic references trong bytecode. Method không chỉ được nhận biết bằng tên; JVM còn dùng **owner, name và descriptor**.

Các descriptors mẫu:

~~~text
id():String        -> ()Ljava/lang/String;
render(Object)     -> (Ljava/lang/Object;)Ljava/lang/String;
render(String)     -> (Ljava/lang/String;)Ljava/lang/String;
~~~

**JVM method descriptor bao gồm return type.** Vì vậy đổi return type hoặc parameter types có thể làm mất descriptor mà binary cũ cần, ngay cả khi tên method giữ nguyên. Java source overload resolution diễn ra lúc compile; binary cũ không tự chọn overload mới khi library update.

Các lỗi thường gặp:

| Runtime lỗi | Nguyên nhân gợi ý |
| --- | --- |
| `NoSuchMethodError` | Binary tham chiếu method/descriptor không còn được resolve |
| `NoSuchFieldError` | Field symbolic reference không còn |
| `IncompatibleClassChangeError` | Thay đổi class/interface hoặc instance/static expectation không tương thích |
| `IllegalAccessError` | Access sau cập nhật không còn hợp lệ cho binary |
| `AbstractMethodError` | Invocation cần concrete implementation nhưng runtime thiếu |
| `NoClassDefFoundError` | Required class không thể tìm/định nghĩa ở runtime |
| `ClassCastException` | Runtime object không đáp ứng type mà caller cast, có thể do wrapper/loader |

Đó là **ví dụ các failure modes**, không phải bảng ánh xạ một lỗi sang đúng một thay đổi duy nhất. Cần kiểm descriptor, class hierarchy, classpath và classloader trước khi quy kết.

**Một binary có thể load thành công nhưng chỉ lỗi khi chạm vào method cũ**. Vì vậy test chỉ khởi động chương trình mà không gọi các public methods quan trọng là chưa đủ.

## 6. Thực nghiệm Java 17: cùng một client, ba phiên bản thư viện

Thí nghiệm thực hiện đúng hai chiều:

- Giữ **Client.class đã compile với v1** và chạy trên libraries v1/v2/v3.
- Giữ **Client.java không sửa** nhưng compile lại với v2 và thử compile với v3.

Kết quả cho thấy **source, binary và behavior không tương đương**. Đây là thử nghiệm Java thuần về ABI; nó không giả lập rằng `javac` có một structural weaver. Tuy nhiên, introductions trong một AOP engine phải tôn trọng các nguyên lý liên kết này nếu client đã được compile chống hợp đồng được weave.

### 6.1. Library v1 — `PublicApi.java`

~~~java
public final class PublicApi {
    public String id() { return "id-v1"; }
    public String render(Object input) { return "Object-v1"; }
}
~~~

### 6.2. Library v2 — cùng binary name, thêm overload

~~~java
public final class PublicApi {
    public String id() { return "id-v2"; }
    public String render(Object input) { return "Object-v2"; }
    public String render(String input) { return "String-v2"; }
}
~~~

### 6.3. Library v3 — bỏ method `id()`

~~~java
public final class PublicApi {
    public String render(Object input) { return "Object-v3"; }
    public String render(String input) { return "String-v3"; }
}
~~~

### 6.4. Client dùng ở cả ba giai đoạn

~~~java
public final class Client {
    public static void main(String[] args) {
        PublicApi api = new PublicApi();
        try {
            System.out.println("ID " + api.id());
        } catch (NoSuchMethodError error) {
            System.out.println("LINKAGE NoSuchMethodError id()");
        }
        System.out.println("RENDER " + api.render(null));
    }
}
~~~

Đây là **mã chạy thật** sau khi compile trong thư mục phù hợp. Catch `NoSuchMethodError` chỉ nhằm làm rõ thí nghiệm, **không phải mẫu xử lý production**. Nếu production gặp linkage error, cần sửa dependency/artifact/ABI thay vì im lặng bỏ lỗi.

### 6.5. Script PowerShell tái hiện toàn bộ và tự dọn dữ liệu tạm

Yêu cầu Windows PowerShell 5.1+ và JDK 17+ có `javac`/`java` trên PATH. Script viết 4 source files vào thư mục tạm, xây 3 library versions và 2 client versions, chạy và kiểm trường hợp compilation thất bại. Các lệnh đều dùng đường dẫn tạm; không chỉnh sửa project.

~~~powershell
$ErrorActionPreference='Stop'
$root=Join-Path $env:TEMP ('aop-compat-'+[guid]::NewGuid().ToString('N'))
$enc=New-Object System.Text.UTF8Encoding($false)
try {
  foreach($dir in @('src-v1','src-v2','src-v3','src-client','v1','v2','v3','client-v1','client-v2','client-v3')) {
    [void](New-Item -ItemType Directory -Force -Path (Join-Path $root $dir))
  }
  function Put([string]$relative,[string]$value) {
    [IO.File]::WriteAllText((Join-Path $root $relative),$value,$enc)
  }
  Put 'src-v1/PublicApi.java' @'
public final class PublicApi {
    public String id() { return "id-v1"; }
    public String render(Object input) { return "Object-v1"; }
}
'@
  Put 'src-v2/PublicApi.java' @'
public final class PublicApi {
    public String id() { return "id-v2"; }
    public String render(Object input) { return "Object-v2"; }
    public String render(String input) { return "String-v2"; }
}
'@
  Put 'src-v3/PublicApi.java' @'
public final class PublicApi {
    public String render(Object input) { return "Object-v3"; }
    public String render(String input) { return "String-v3"; }
}
'@
  Put 'src-client/Client.java' @'
public final class Client {
    public static void main(String[] args) {
        PublicApi api = new PublicApi();
        try {
            System.out.println("ID " + api.id());
        } catch (NoSuchMethodError error) {
            System.out.println("LINKAGE NoSuchMethodError id()");
        }
        System.out.println("RENDER " + api.render(null));
    }
}
'@
  foreach($i in 1..3) {
    & javac --release 17 -encoding UTF-8 -d (Join-Path $root "v$i") (Join-Path $root "src-v$i/PublicApi.java")
    if($LASTEXITCODE -ne 0){throw "compile v$i failed"}
  }
  & javac --release 17 -encoding UTF-8 -cp (Join-Path $root 'v1') -d (Join-Path $root 'client-v1') (Join-Path $root 'src-client/Client.java')
  if($LASTEXITCODE -ne 0){throw 'compile client-v1 failed'}
  Write-Output 'RUN existing client + v1'
  & java -cp ((Join-Path $root 'client-v1')+';'+(Join-Path $root 'v1')) Client
  if($LASTEXITCODE -ne 0){throw 'run client+v1 failed'}
  Write-Output 'RUN existing client + v2'
  & java -cp ((Join-Path $root 'client-v1')+';'+(Join-Path $root 'v2')) Client
  if($LASTEXITCODE -ne 0){throw 'run client+v2 failed'}
  & javac --release 17 -encoding UTF-8 -cp (Join-Path $root 'v2') -d (Join-Path $root 'client-v2') (Join-Path $root 'src-client/Client.java')
  if($LASTEXITCODE -ne 0){throw 'compile client-v2 failed'}
  Write-Output 'RUN rebuilt client + v2'
  & java -cp ((Join-Path $root 'client-v2')+';'+(Join-Path $root 'v2')) Client
  if($LASTEXITCODE -ne 0){throw 'run new client+v2 failed'}
  Write-Output 'RUN existing client + v3'
  & java -cp ((Join-Path $root 'client-v1')+';'+(Join-Path $root 'v3')) Client
  if($LASTEXITCODE -ne 0){throw 'run client+v3 failed'}
  $ErrorActionPreference='Continue'
  $diagnostic=& javac --release 17 -encoding UTF-8 -cp (Join-Path $root 'v3') -d (Join-Path $root 'client-v3') (Join-Path $root 'src-client/Client.java') 2>&1
  $status=$LASTEXITCODE
  $ErrorActionPreference='Stop'
  if($status -eq 0){throw 'recompile unexpectedly succeeded'}
  Write-Output 'RECOMPILE original source + v3 FAILED (expected)'
  Write-Output 'ALL COMPATIBILITY CHECKS PASSED'
}
finally {
  if(Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
~~~

Đầu ra **đã kiểm chứng bằng biên dịch và chạy thực với JDK 17**:

~~~text
RUN existing client + v1
ID id-v1
RENDER Object-v1
RUN existing client + v2
ID id-v2
RENDER Object-v2
RUN rebuilt client + v2
ID id-v2
RENDER String-v2
RUN existing client + v3
LINKAGE NoSuchMethodError id()
RENDER Object-v3
RECOMPILE original source + v3 FAILED (expected)
ALL COMPATIBILITY CHECKS PASSED
~~~

### 6.6. Đọc bốn trường hợp

1. **V1 binary + V1 library:** `id()` tồn tại; `render(null)` đã compile thành `render(Object)`, kết quả `Object-v1`.
2. **V1 binary + V2 library:** symbolic reference của lời `render(null)` trong binary cũ vẫn là `render(Object)`, kết quả `Object-v2`; overload String mới không thay bytecode cũ.
3. **Client source rebuild + V2 library:** javac thấy thêm `render(String)` và chọn overload cụ thể hơn, kết quả `String-v2`. Source vẫn compile, **behavior thay đổi**.
4. **V1 binary + V3 library:** binary gọi `id()` đã bị xóa nên phát sinh `NoSuchMethodError`; phần catch của bài học in tên lỗi. Compile lại Client source với v3 thất bại do thiếu `id()`.

Thử nghiệm làm rõ một vấn đề cốt lõi khi version một structural aspect: **một introduction bổ sung overloaded member có thể không phá binary cũ nhưng thay đổi behavior của client khi rebuild**. Ngược lại, xóa một member đã được client compile phụ thuộc có thể phá cả hai.

## 7. Một introduction interface/method ảnh hưởng compile-time và runtime ra sao?

Giả sử `Order` ban đầu không implements `Trackable`.

~~~text
RAW:
  Order implements BusinessEntity

WRAPPER:
  OrderProxy implements BusinessEntity, Trackable
  Order raw class giữ nguyên

WOVEN (nếu công cụ hỗ trợ):
  Order implements BusinessEntity, Trackable
  method trackingId() nằm trong woven class
~~~

**Đừng đánh đồng wrapper với woven target class**. Nếu caller giữ raw `Order` thì cast `Trackable` không tự thành công chỉ vì một proxy khác có interface ấy. Nếu source compiler không được cung cấp introduced type contract, nó cũng không tự cho phép `new Order().trackingId()`.

### 7.1. Mã nguồn downstream phải nhìn thấy hợp đồng

Cần xác định:

- Introduction được áp dụng ở compile-time, binary weaving hay load-time?
- Compiler của client nhìn **raw source**, **woven classfile**, **generated declarations** hay một interface API rõ?
- IDE, incremental build, language server có hiểu thông tin mới không?
- Module chạy dùng cùng artifact đã compile không?
- Một module khác có thể dùng raw JAR và tạo type identity khác không?

**Client compile với woven API nhưng chạy raw JAR** là một kiểu mismatch dễ gây lỗi linkage/runtime; không thể khắc phục chỉ bằng unit test advice logic.

### 7.2. Khi binary cũ chạy trên woven class mới

Nếu member mà binary cũ cần vẫn giữ nguyên, lời gọi có thể chạy. Nhưng introduced interface có thể đổi behavior ngoài ý định: `instanceof Trackable` bắt đầu true; reflective serializer thấy getter mới; behavioral pointcut có thể match những methods mới.

### 7.3. Khi binary mới chạy trên raw class cũ

Một client mới compile gọi `Order.trackingId()` có thể gặp lỗi nếu runtime nạp `Order` raw chưa có method. Đây là **lỗi artifact compatibility**, không nhất thiết do business code sai. Phải test cả **new-client + expected woven artifact** và **old-client + new woven artifact**.

## 8. Ma trận thay đổi cấu trúc và mức rủi ro

Bảng chỉ là **định hướng kiểm thử**; quy tắc chi tiết còn phụ thuộc JLS, JVM và mô hình AOP.

| Thay đổi | Nguy cơ source | Nguy cơ binary | Vấn đề bổ sung |
| --- | --- | --- | --- |
| Thêm method tên mới | Thường ít nếu không conflict | Thường giữ old references | API discovery/reflection đổi |
| Thêm overload | Có thể source vẫn compile nhưng binding khác hoặc ambiguous | Old descriptors thường còn | Semantic drift khi recompile |
| Xóa/đổi tên member cũ | Client cũ có thể không compile | Có thể `NoSuchMethodError`/`NoSuchFieldError` | Migration |
| Đổi return/parameter types | Source call hoặc assignments có thể fail | Descriptors thay | Bridge/generics |
| Đổi instance↔static | Cách invocation thay | Có thể `IncompatibleClassChangeError` | Inheritance semantics |
| Thu hẹp visibility | Compilation access lỗi | Có thể `IllegalAccessError` | Module boundaries |
| Thêm interface | Type checking/method conflicts | Tùy resolution/hierarchy | `instanceof`, overload, reflection |
| Thêm abstract method vào interface | Implementors mới có thể phải bổ sung | Có thể lỗi khi invocation trên old implementor | Default/abstract semantics |
| Thêm default method | Một số cases compile lại không đúng | Có thể đổi method resolution | Diamond conflicts |
| Thêm field | Thường ít ảnh hưởng source references cũ | Old field descriptors thường còn | Serialization, ORM |
| Thêm interface trên proxy | Raw target source không đổi | Caller phải có wrapper đúng | Object identity, alias |
| Dệt before/after giữ method descriptors | Source API thường không đổi | Linkage có thể giữ | Exceptions/performance/side effects |
| Thay class hierarchy | Có thể đổi casts/overloads | Có thể lỗi method/class resolution | Dispatch và binary identity |

Không suy từ “đều là additive change” rằng một migration an toàn với **mọi** clients. Cần biết overloads, inheritance graph, raw/woven artifacts và điểm quan sát.

## 9. Cơ chế weaving và giới hạn của JVM class schema

Một structural declaration có thể được áp dụng trước khi JVM định nghĩa class:

~~~text
Source or existing binary
         |
         +-> compile-time / binary weaving
         +-> load-time transform (trước defineClass)
         |
         v
      JVM class definition + verification
         |
         v
      Class objects / instances
~~~

Một Java agent có thể biến đổi bytecode, nhưng **redefinition/retransformation một class đã được định nghĩa** qua Instrumentation API thông thường có giới hạn về **schema changes**: không tự do thêm/bớt methods/fields, đổi signatures hay inheritance. Không suy từ khả năng đổi method body lúc chạy rằng có thể hot-add interface vào bất kỳ loaded class nào.

### 9.1. Build-time và load-time có rủi ro khác nhau

- **Build-time weaving:** dễ xác định woven artifact trước khi publish, nhưng phải quản lý compiler, cache và artifact provenance.
- **Load-time weaving:** linh hoạt hơn khi nạp class, nhưng phụ thuộc transformer/agent startup, classloader, thứ tự định nghĩa class và chính sách runtime.
- **Runtime proxy:** không đổi target class schema, nhưng chỉ các lời gọi qua proxy và contract của proxy được can thiệp.
- **Existing loaded class:** structural schema đổi trực tiếp có thể không hỗ trợ, nên restart/redeploy có thể cần.

**Class definition**, **class initialization**, **aspect instantiation** và **advice invocation** là bốn mốc riêng; không đồng nhất chúng.

### 9.2. Defining classloader là một phần của type identity

Cùng binary class name nhưng do hai defining classloaders khác nhau tạo ra có thể là hai runtime types khác nhau. Trong plugin systems, module A có woven `Order` còn module B có raw `Order`; casting hoặc reflective matching có thể không hoạt động như mong muốn.

Khi debug, ghi **binary name + defining classloader + artifact hash/version**, không chỉ tên class.

## 10. Reflection và API discovery có thể đổi hành vi ngầm

Một structural introduction thêm `getAuditId()` hoặc field `auditId` có thể được các công cụ reflection khám phá:

- JSON serializer nhận property mới theo convention.
- ORM mapping scan field/getter mới.
- Plugin registry dò interface vừa được thêm.
- Schema generator tìm methods/annotations mới.
- RPC endpoint scanner có thể xem interface mới.
- Observability tool có thể đếm methods/annotations khác đi.

Không phải mọi framework sẽ tự phản ứng như nhau; điều đó tùy cấu hình. Nhưng **reflective surface** là một dạng hợp đồng quan trọng ngoài source/binary compatibility.

### 10.1. Kiểm đúng lớp

- `Core.class` raw: các members class raw thực sự khai báo.
- `proxy.getClass()`: các interfaces/methods của proxy.
- Woven `Core.class`: type đã được engine thay đổi nếu có.
- Static type client được compile dựa vào: có thể không biết một introduced method.

`getMethods()` liệt kê public methods theo reflection rules, gồm inherited public methods; `getDeclaredMethods()` liệt kê methods **được khai báo trực tiếp** trong class. Không đếm đơn giản methods và cho đó là bằng chứng weaving đúng; còn synthetic/bridge methods do compiler sinh.

### 10.2. Bridge và synthetic methods

Với generic overrides, compiler có thể tạo bridge methods để duy trì method dispatch sau erasure. Một weaver cũng có thể bổ sung helpers synthetic. Khi so public ABI, kiểm method descriptor và flags, không suy “hai methods cùng tên tức introduction bị chạy trùng”.

## 11. Serialization compatibility và data schema

Một introduced field/property có thể làm dữ liệu được serialize thay đổi dù binary caller vẫn chạy. Đối với Java native serialization, nếu class dùng `serialVersionUID` tính mặc định thì thay đổi class shape có thể ảnh hưởng version UID; ngay cả `serialVersionUID` cố định cũng **không biến mọi data schema change thành an toàn**.

Những tình huống cần test:

- Serialized data từ bản cũ đọc bằng bản mới.
- Dữ liệu mới đọc bởi bản cũ nếu rollback/older clients là yêu cầu.
- Property vừa được introduce có default/backfill thích hợp không.
- Getter mới có lộ secrets hoặc tạo cycles trong object graph không.
- ORM có map field mới ngoài dự kiến không.
- Binary class name/type hierarchy đã thay có ảnh hưởng serializer không.
- JSON schema/protocol compatibility của hệ thống bên ngoài có chính sách riêng không.

**Compatibility của persisted data khác compatibility của method invocation.** Chỉ test `javac` và `java` chưa chứng minh schema migration đúng.

## 12. Introduced member và xung đột với cấu trúc đang có

### 12.1. Name collision

Nếu một target đã khai báo `trackingId()` với ý nghĩa riêng, còn aspect giới thiệu `trackingId()` khác, không thể để hai implementations tranh cùng contract mà không có rule cụ thể. Một số công cụ báo conflict, một số có precedence hoặc visibility riêng.

**Thiết kế tốt:** giới hạn type selectors, đặt tên member có ý nghĩa domain, xây positive/negative tests và fail build khi xung đột chưa được quyết định.

### 12.2. Generic erasure

`List<String>` và `List<Integer>` có cùng erased raw type `List`. Không mặc định hai introduced methods chỉ khác generic type arguments đều tạo overload hợp lệ. Kiểm cả generic signature metadata lẫn JVM descriptors.

### 12.3. Interface default methods

Thêm interface mới có thể làm object đáp ứng một capability mà các thư viện khác tự khám phá. Nếu hai defaults cùng signature cạnh tranh theo hierarchy, compiler/runtime phải có resolution phù hợp. Từng engine có thể giới hạn introductions; không tuyên bố khả năng thêm interface là không điều kiện.

### 12.4. Visibility, modules và `final`

Một subclass proxy không thể subclass Java `final` class bình thường, nhưng bytecode weaving vào một method body và thay type relationship là những cơ chế khác. Java modules, package accessibility, private members, verifier và classloader constraints đều cần xét.

Không suy từ một hạn chế của proxy rằng mọi kiểu weaving đều bị giới hạn y hệt.

## 13. Binary surface khi structural weaving đổi hoặc rút đi

Khi một introduced API đã được client compile sử dụng, nó trở thành **API thật** đối với client ấy, dù source `Order.java` không khai báo rõ.

Nếu version mới:
- Xóa introduction `trackingId()`;
- Chỉ để method ở một proxy thay vì woven target;
- Đổi return type hoặc field type;
- Thay target selector nên một số classes không còn được introduce;

thì **client binaries cũ có thể tham chiếu API biến mất**. Lỗi có thể chỉ xuất hiện ở một đường gọi hiếm, khi production thật gọi method đó.

Nguyên tắc: **các public introductions phải được quản lý version như public source methods**. Chúng không “riêng tư” chỉ vì nằm trong file aspect.

## 14. Bảo trì: giảm boilerplate không đồng nghĩa giảm tổng chi phí

Một structural aspect có thể thay hàng trăm lần chỉnh source, nhưng mang thêm chi phí:

1. **Discoverability:** mở `Order.java` không thấy method đang hiện diện trong woven class.
2. **Tooling:** IDE/compiler/static analysis phải hiểu introduction.
3. **Build:** bước weaving, source generation, incremental cache và dependency graph phải chính xác.
4. **Testing:** thêm các tests source/binary/reflective và woven/raw artifact.
5. **Debugging:** stacktrace có proxy, synthetic methods hoặc classloader mismatch.
6. **Deployment:** agent/load ordering và artifact version cần kiểm.
7. **Versioning:** clients có thể compile dựa trên methods được introduced mà thư viện không nhìn thấy trực tiếp.
8. **Onboarding:** developer mới cần hiểu crosscutting type contract và join point behavior.
9. **Migration:** thay engine AOP hoặc rút introduction phải có compatibility shim.
10. **Security/data contracts:** interface mới có thể mở capabilities và serializer properties.

Ngược lại, lợi ích có thật khi nhiều types cần **một contract nhất quán**, quy tắc nằm ở một nơi, compiler/weaver đáng tin và test suite có kiểm soát.

### 14.1. Khung đánh giá chi phí định tính

~~~text
Total maintenance cost ≈
  initial implementation
+ weaving/build/IDE maintenance
+ compatibility verification
+ debugging and observability
+ deployment/rollback costs
+ future migration costs
− duplicated declarations removed
− consistency errors prevented
~~~

Đây chỉ là **mô hình suy nghĩ**, không phải công thức định lượng chung. Điểm cần xem là **blast radius** của một introduction: chọn tất cả types trong package rộng có thể tự mở rộng khi class mới xuất hiện.

### 14.2. Cùng một concern có thể dùng adapter thay vì introduction

Nếu chỉ một API boundary cần `Tagged`, wrapper implementation của `Tagged` có thể dễ bảo trì. Nếu toàn bộ codebase thực sự yêu cầu `Order` ở type-level phải đáp ứng `Trackable` và compiler/tooling hỗ trợ tốt, structural introduction có thể có lợi.

Không nên chọn weaving khi sửa source trực tiếp hoặc composition đơn giản hơn, nhưng cũng không nên phủ nhận lợi ích của một contract cắt ngang được kiểm soát.

## 15. Thiết kế migration cho API được introduce

Nếu muốn đổi `trackingId()` sang `traceId()`, **xóa ngay** method cũ là rủi ro đối với client source và binaries.

Một chiến lược chuyển tiếp có thể là giữ method cũ và forward:

~~~java
interface Trackable {
    String traceId();

    @Deprecated
    default String trackingId() {
        return traceId();
    }
}
~~~

Đây là fragment Java hợp lệ minh họa **API deprecation**, không phải đảm bảo mọi client đã compile với introduced `Order.trackingId()` sẽ link. Cần kiểm **binary owner/descriptor cũ**: một default method trên interface có thể hoặc không thỏa call site cũ, tùy method resolution và nơi method từng được giới thiệu. Đôi khi phải giữ một delegating method đúng contract cũ ngay trên woven class.

Các bước chuyển tiếp:

1. Công bố contract mới.
2. Giữ compatibility shim của member cũ nếu feasible.
3. Build old clients và chạy trên new artifact.
4. Cập nhật clients theo từng release.
5. Giám sát usage của API deprecated.
6. Chỉ xóa khi consumers đã di trú hoặc version policy cho phép breaking change.
7. Ghi hướng rollback cho cả code và serialized data.
8. Nếu bỏ weaving, chuyển sang explicit interface/adapter hoặc source declaration có khả năng giữ ABI.

## 16. Ma trận test cần có

| Nhóm | Test cụ thể |
| --- | --- |
| Source | Compile lại client source cũ với woven API mới |
| Binary | Chạy client `.class` cũ với library mới |
| Overload | `null`, generic/primitive overload selection và ambiguity |
| Introduction | `instanceof`, method/field signatures, visibility |
| Negative coverage | Classes không được chọn không nhận interface/member |
| Reflection | `getMethods`, `getDeclaredMethods`, `isAssignableFrom` |
| Serialization | Old data → new version, new data → old version nếu yêu cầu |
| Behavioral | Advice order, exceptions, retry, cached results, side effects |
| Proxy | Client đi qua proxy vs raw target; self-invocation |
| Weaving | Đúng classfile đã weave, agent/classloader đúng thời điểm |
| Deployment | Không nhầm raw/woven JAR, version mismatch |
| Rollback | Woven→raw, API removed, data schema compatibility |
| Concurrency | Introduced state có thread-safe và lifecycle đúng |
| Build | IDE/CLI cùng nhìn API, incremental build không dùng stale output |

**Bắt buộc kiểm cả positive lẫn negative coverage.** Chỉ assert `Order` có `Trackable` chưa đủ; có thể `SecretToken` hoặc type không liên quan cũng vô tình được introduce bởi pattern quá rộng.

### 16.1. Không mock mất điều đang cần test

Unit test một behavioral advice khi gọi trực tiếp method handler không chứng minh structural weaver đã chạy. Tương tự, test một proxy implements interface mới không chứng minh raw target class thực sự bị thay cấu trúc.

Integration test phải dùng **artifact/runtime mechanism thực** trong phạm vi khả thi.

## 17. Dùng `javap` và ABI snapshots để thấy khác biệt

JDK có công cụ `javap` cho phép kiểm method signatures/descriptors:

~~~bash
javap -p -s PublicApi
~~~

Để so ba thư viện của ví dụ, đặt classpath tới thư mục library tương ứng; kiểm `id()Ljava/lang/String;` và hai overload `render(...)Ljava/lang/String;`.

Một ABI baseline có thể ghi:

~~~text
PublicApi:
  id()Ljava/lang/String;
  render(Ljava/lang/Object;)Ljava/lang/String;
~~~

Phiên bản mới thêm:

~~~text
  render(Ljava/lang/String;)Ljava/lang/String;
~~~

Xóa `id()` ở phiên bản sau là một ABI diff có nguy cơ breaking. Nếu dùng structural weaving, **chụp ABI của woven classfiles**, không chỉ raw source. Có thể thêm automated compatibility checks trong CI nhưng vẫn phải test hành vi.

### 17.1. Build provenance

Khi `NoSuchMethodError` xuất hiện, cần xác định:

- Method owner/name/descriptor được client yêu cầu.
- Client compile với library version nào.
- Runtime đã nạp classfile nào.
- Woven hay raw artifact?
- Defining classloader nào?
- Weaver/agent có chạy trước defineClass không?
- Module/classpath có cả hai versions không?
- Aspect type selectors có loại class khỏi introduction không?

Không vội sửa bằng cách “thêm try/catch” hoặc tăng timeout; đây là lỗi compatibility hoặc deployment cần giải quyết ở nguồn.

## 18. Behavioral compatibility cũng chịu tác động của structural change

Khi giới thiệu method/interface mới, các behavioral aspects có thể:

- Match vào method mới do pointcut quá rộng.
- Ghi event audit mới cho một lời gọi mà trước đây không tồn tại.
- Làm metrics count tăng do thêm synthetic/bridge methods.
- Thay advice precedence nếu introduce method kéo thêm một layer.
- Khiến serializer/reflection gọi introduced getters và kích hoạt code có side effects.
- Làm một branch `instanceof` bắt đầu chạy.
- Cho phép caller mới dùng một capability có rủi ro bảo mật.

Do đó kiểm structural ABI xong **chưa đủ**. Test behavioral side effects, exception propagation, timing và những đối tượng không được chọn.

### 18.1. Binary compatibility có thể vẫn giữ mà hành vi đổi

Trong thử nghiệm v1/v2, `Client.class` cũ vẫn chạy với v2; method `render(Object)` tồn tại, nên ABI call không bị mất. Nhưng implementation của nó đã đổi từ `Object-v1` sang `Object-v2` dù signature không đổi. Một advice chèn thêm retry thậm chí có thể làm target execute hai lần và tạo side effect trùng.

**Một thư viện tương thích nhị phân không phải thư viện giữ nguyên nghĩa vụ nghiệp vụ.**

## 19. Những hiểu lầm thường gặp

1. **“Compile source xanh tức binary cũ chắc chạy.”** Không; phải chạy old binaries.
2. **“Binary cũ chạy tức source rebuild chọn cùng overload.”** Không; overload resolution diễn ra khi compile.
3. **“Thêm method luôn an toàn.”** Có thể có overload ambiguity và semantic drift.
4. **“Giảm số dòng code luôn giảm maintenance cost.”** Weaving/build/compatibility có chi phí riêng.
5. **“Một introduction chỉ là advice before.”** Không; nó thay đổi contract của type nếu engine thực hỗ trợ.
6. **“Bytecode weaving nào cũng sửa type hierarchy.”** Không; behavioral weaving có thể chỉ sửa instructions.
7. **“Proxy implements Tagged nghĩa target implements Tagged.”** Không.
8. **“Client compiler tự thấy method sẽ weave sau.”** Không nếu không có type information/tooling.
9. **“NoSuchMethodError có thể catch như lỗi validation.”** Đây là lỗi linkage, không phải policy xử lý nghiệp vụ bình thường.
10. **“Chỉ so tên method là đủ.”** JVM dùng owner/descriptors/access/kind.
11. **“Return type không có trong JVM descriptor.”** Sai.
12. **“Một class name luôn chỉ một runtime type.”** Còn defining loader.
13. **“Hot reload có thể thêm mọi field/interface ở loaded class.”** Instrumentation schema có giới hạn.
14. **“Raw artifact test đủ cho woven production.”** Không.
15. **“Giới thiệu getter không ảnh hưởng serializer.”** Có thể làm thay property discovery.
16. **“Một default method mới không thể gây conflict.”** Sai trong các hierarchy phù hợp.
17. **“Giữ serialVersionUID nghĩa mọi schema change an toàn.”** Không.
18. **“ABI pass nghĩa advice behavior pass.”** Không.
19. **“Thay method trong aspect không phải public API change.”** Nếu clients gọi introduced member, nó là API thực.
20. **“Đổi loader không ảnh hưởng casting.”** Runtime identity phụ thuộc loader.
21. **“Module compile woven, module khác compile raw chắc tương đương.”** Không.
22. **“Một structural rule match rộng sẽ không ảnh hưởng classes mới.”** Nó có thể tự match classes được thêm.
23. **“Bỏ structural weaver chỉ xóa dependency.”** Client APIs, artifact và reflection còn phụ thuộc nó.
24. **“Add interface không đổi behavior.”** `instanceof`, dispatch và reflection có thể đổi.
25. **“Chỉ test client mới với library mới là đủ.”** Old-client/new-library bắt lỗi binary compatibility.
26. **“Xóa method cũ ngay vì đã deprecated.”** Old binaries có thể vẫn cần nó.
27. **“Wrapper và woven target có cùng identity.”** Chúng thường là hai objects hoặc types khác nhau.
28. **“Source compatibility bảo đảm serializer schema.”** Không.
29. **“Chạy không lỗi lúc startup là ABI an toàn.”** Một missing method có thể chỉ bị resolve khi gọi.
30. **“Một test `instanceof` duy nhất chứng minh structural introduction đúng.”** Cần cả chính xác types được/không được chọn, descriptors và toolchain.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Source compatibility khác binary compatibility thế nào?  
**Đáp án:** Source hỏi có thể compile lại source cũ không; binary hỏi compiled client cũ có resolve/run với library mới không.

**Câu 2.** V2 thêm `render(String)`, binary client compile với v1 có tự gọi overload mới không?  
**Đáp án:** Không, descriptor của call cũ vẫn là `render(Object)`.

**Câu 3.** Vì sao rebuild client source cũ với v2 lại in `String-v2`?  
**Đáp án:** `javac` chọn overload `String` cụ thể hơn khi truyền `null`.

**Câu 4.** V3 bỏ `id()`, binary client cũ có thể gặp lỗi gì?  
**Đáp án:** `NoSuchMethodError` khi lời gọi cần method cũ.

**Câu 5.** Thêm interface cho proxy có thêm interface vào raw target class không?  
**Đáp án:** Không, chỉ proxy object mang contract đó.

**Câu 6.** Tại sao source compiler chưa thấy introduction thì không thể gọi method mới trực tiếp?  
**Đáp án:** Compiler cần type information ở thời điểm compile, không tự biết method sẽ được weave về sau.

**Câu 7.** Có cần kiểm reflection khi structural introduction thêm field/getter không?  
**Đáp án:** Có, vì serializer/ORM/schema scanner có thể quan sát sự thay đổi.

**Câu 8.** `serialVersionUID` cố định có bảo đảm dữ liệu cũ và mới luôn tương thích?  
**Đáp án:** Không; còn type/field/schema và custom serialization contracts.

**Câu 9.** Một class đã load có chắc hot-add field qua Java Instrumentation API thông thường không?  
**Đáp án:** Không; schema changes của redefinition/retransformation có giới hạn.

**Câu 10.** Vì sao cùng tên class có thể không cast được giữa hai plugins?  
**Đáp án:** Defining classloader khác tạo runtime type identity khác.

**Câu 11.** Có thể giữ ABI nhưng vẫn phá behavioral contract không?  
**Đáp án:** Có, ví dụ đổi implementation, thêm advice retry hoặc overload được chọn khác sau recompilation.

**Câu 12.** Trước khi xóa introduced `trackingId()` cần làm gì?  
**Đáp án:** Kiểm consumers, giữ compatibility shim nếu khả thi, test binaries cũ và lập migration/rollback.

## 21. Checklist trước khi phát hành một structural aspect

- [ ] Xác định type được chọn và type **không** được chọn.
- [ ] Ghi rõ member/interface/field mới cùng descriptor, visibility và lifecycle.
- [ ] Kiểm xung đột name, generics erasure, defaults, inheritance và access.
- [ ] Xác định compiler/source processing thấy introduction ở giai đoạn nào.
- [ ] Build consumer source cũ chống woven artifact mới.
- [ ] Chạy compiled client cũ chống woven artifact mới.
- [ ] Test overload selection sau khi biên dịch lại.
- [ ] So public ABI của woven artifacts, không chỉ raw source.
- [ ] Test `instanceof`/reflection trên đúng proxy hoặc target class.
- [ ] Test serializer/ORM và dữ liệu phát hành cũ.
- [ ] Kiểm aspect mới có làm behavioral pointcut match thêm methods không.
- [ ] Kiểm exception/result/side effect của những lời gọi đã tồn tại.
- [ ] Đảm bảo CI artifact giống artifact phát hành.
- [ ] Không trộn raw/woven JAR sai version trong classpath/module path.
- [ ] Kiểm load-time transformer/agent trước class definition nếu cần.
- [ ] Kiểm classloader/module boundaries của ứng dụng.
- [ ] Xem xét concurrency nếu introduced field có trạng thái mutable.
- [ ] Ghi deprecation/migration path cho API public bị đổi.
- [ ] Có rollback plan cho cả code và data schema.
- [ ] Theo dõi linkage errors/serializer changes sau triển khai.

## 22. Tổng kết

**Tương thích mã nguồn, tương thích nhị phân, tương thích hành vi và chi phí bảo trì** là các trục đánh giá riêng khi AOP thay đổi cấu trúc. Một introduction có thể bổ sung contract cho nhiều types, nhưng cũng tạo rủi ro xung đột method, lệch raw/woven artifact, lỗi JVM linkage, thay overload selection và làm reflection/serialization công bố API mới. Một proxy mở rộng interface chỉ cho **proxy** không đồng nghĩa class target đã được biến đổi.

Thử nghiệm Java 17 cho thấy: client binary cũ **giữ nguyên descriptor** khi library thêm overload; cùng source compile lại có thể chọn overload khác; xóa method cũ dẫn đến `NoSuchMethodError` và source compilation failure. Vì vậy khi quản lý structural AOP như một public API, cần **test client cũ ở cả dạng source và binary trên artifact mới**, đồng thời kiểm behavioral regressions, classloaders, reflective surface và khả năng rollback.

Giá trị của aspect nằm ở khả năng mô-đun hóa concern một cách có chủ đích, không phải biến đổi chương trình mà không cần chịu trách nhiệm về compatibility. **Thiết kế tốt làm rõ ai thấy type contract mới, khi nào nó tồn tại và chi phí vận hành của nó trong suốt vòng đời phiên bản.**