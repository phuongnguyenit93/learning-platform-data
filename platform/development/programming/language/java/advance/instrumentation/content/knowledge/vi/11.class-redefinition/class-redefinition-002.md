# Chọn redefine hay retransform theo nguồn byte và mục tiêu thay đổi

## 1. Câu hỏi quan trọng nhất: bạn đang có bytecode mới hay muốn biến đổi bytecode hiện có?

Cả `Instrumentation.redefineClasses(...)` và `Instrumentation.retransformClasses(...)` đều có thể tác động lên **class đã được JVM nạp**, nhưng chúng không phải hai cách gọi tương đương của cùng một hành động. Cách chọn đúng bắt đầu từ **nguồn classfile bytes** và **điều bạn thực sự muốn thay đổi**.

- **Redefinition:** bạn đã chuẩn bị **một định nghĩa classfile thay thế** cho đúng class đang chạy — chẳng hạn tệp `.class` được biên dịch lại từ source sau khi sửa lỗi, hoặc bytes mới từ quy trình hot-patch có kiểm soát. Bạn đưa đầy đủ bytes đó qua `new ClassDefinition(targetClass, replacementBytes)` vào `redefineClasses(...)`.
- **Retransformation:** bạn có một hoặc nhiều `ClassFileTransformer` và muốn JVM **chạy lại pipeline biến đổi** trên class đã nạp; input cơ sở do JVM cung cấp từ lần định nghĩa ban đầu hoặc **lần redefine gần nhất**. Bạn yêu cầu `retransformClasses(targetClass)`, rồi các transformer retransformation-capable được gọi để tạo bytes biến đổi.

**Không có quy tắc “redefine mạnh hơn retransform”.** Mỗi cơ chế xử lý một kiểu nguồn dữ liệu và workflow khác nhau. Cả hai đều phải đi qua các giới hạn sửa class của JVM; không dùng một API để lách những hạn chế của API còn lại.

### Bốn tình huống mở đầu

| Tình huống | Cách nên cân nhắc | Vì sao |
|---|---|---|
| Dev vừa biên dịch lại `OrderService.class` sau khi sửa logic tính phí và muốn thay method body trong JVM đang chạy | **`redefineClasses`** | Đã có đầy đủ classfile **thay thế** |
| Agent tracing đã cài transformer; muốn bật/tắt instrumentation bằng cách chạy lại logic transformer cho các class được chọn | **`retransformClasses`** | Cần chạy lại **transformation pipeline** trên bytes cơ sở |
| Agent vừa attach rồi đăng ký transformer; những class đã load chưa đổi | **`retransformClasses`** nếu đủ capability | `addTransformer(...)` không tự xử lý lại class đã nạp |
| Muốn thêm field mới hoặc thay superclass để sửa model runtime | **Thường không phải cách nào** | Giới hạn schema của class redefinition/retransformation; cần thiết kế khác như khởi động lại, class-loader replacement hoặc kiến trúc dữ liệu bên ngoài |

**Mục tiêu bài học:** hình dung chính xác nguồn bytes ở cả hai đường, hiểu vai trò transformer ngay cả khi redefine, chọn thao tác phù hợp với tình huống thực tế, kiểm soát lỗi và xác minh behavior. Bài có demo Java 17+ sinh **hai định nghĩa cùng binary name**, thực hiện retransform và redefine có kiểm soát để thấy sự khác biệt giữa “bytes gốc của lần load” và “bytes gốc sau lần redefine”.

## 2. Tách bạch ba khái niệm thường bị trộn lẫn

Một class đang chạy có thể liên quan tới ba dạng bytes:

1. **Bytes đầu vào của lần class definition:** bytes mà loader chuyển cho `ClassLoader.defineClass(...)` (hoặc đường JVM tương đương), trước khi chuỗi transformer được áp dụng.
2. **Bytes đầu vào của lần redefine gần nhất:** classfile do công cụ cung cấp qua `ClassDefinition.getDefinitionClassFile()`; đây là cơ sở mới cho các lượt retransformation về sau.
3. **Bytes hiệu lực sau biến đổi:** kết quả do chuỗi transformer tạo ra sau khi JVM kiểm tra hợp lệ; đây là định nghĩa đang được dùng cho các lời gọi method mới.

Những dạng này có thể trùng nhau hoặc khác nhau:

~~~text
LẦN CLASS LOAD ĐẦU:
loader --[bytes ban đầu]--> transformer chain --> JVM verify --> class đang chạy
             ^
             |-- nguồn cơ sở ban đầu của retransform

REDЕFINE:
tool --[replacement .class bytes]--> transformer chain --> JVM verify --> class đang chạy
             ^
             |-- nguồn cơ sở cho các lượt retransform SAU redefine

RETRANSFORM:
JVM lấy nguồn cơ sở lần load / lần redefine gần nhất
    |
    +-- tự tái áp dụng kết quả của các transformer không capable
    |
    +-- gọi lại các transformer canRetransform=true
    |
    v
JVM verify --> class đang chạy với kết quả mới
~~~

**Chú ý:** bytes cơ sở khi retransform không nhất thiết **byte-for-byte giống** bytes ban đầu trên ổ đĩa. Tài liệu `Instrumentation` cho phép JVM thay đổi bố cục/độ lớn/thứ tự constant pool, bỏ một số attributes không thiết yếu hoặc thay đổi thứ tự các thành phần mà thứ tự không mang ý nghĩa. Một transformer đúng phải đọc đầu vào hiện tại theo định dạng classfile, không so khớp hash với tệp gốc rồi giả định toàn bộ offset là cố định.

## 3. So sánh API theo nguồn bytes và hành vi

| Khía cạnh | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
|---|---|---|
| Input bắt buộc từ caller | Cặp **`Class<?>` + `byte[]`** chứa **full replacement classfile** | **`Class<?>`** cần xử lý lại, không truyền classfile bytes trực tiếp |
| Nguồn bytes cơ sở | `ClassDefinition.getDefinitionClassFile()` do caller cung cấp | Bytes cơ sở từ lần class load hoặc **lần redefine gần nhất** do JVM quản lý |
| Tác dụng chính | Thay class definition theo source mới, phù hợp fix-and-continue/hot patch từ classfile đã chuẩn bị | Yêu cầu JVM chạy lại chuỗi xử lý bytecode cho class đã nạp, phù hợp instrumentation |
| Transformer tham gia? | **Có**: chuỗi transform được chạy trong xử lý redefine | **Có chọn lọc**: transformer `canRetransform=true` được gọi lại; kết quả của transformer không capable được tái dùng |
| Capability riêng | `Can-Redefine-Classes: true` + `isRedefineClassesSupported()` | `Can-Retransform-Classes: true` + `isRetransformClassesSupported()` |
| Điều kiện từng class | `isModifiableClass(c)` | `isModifiableClass(c)` |
| Thay đổi method body phù hợp | Có, nếu định nghĩa mới hợp lệ | Có, nếu transformer trả bytes hợp lệ |
| Tự thêm/xóa field, method, đổi superclass hoặc interfaces? | **Không mặc định được phép**; nhiều kiểu đổi schema bị từ chối | **Không mặc định được phép**; cùng họ giới hạn JVM TI |
| Có tạo lại instances hoặc reset static fields? | Không | Không |
| Active stack frame của method bị đổi | Frame đang chạy có thể tiếp tục dùng bytecode cũ | Tương tự |
| Truyền nhiều class một lượt | `ClassDefinition...`; lỗi → không class nào trong lượt được redefine | `Class<?>...`; lỗi → không class nào trong lượt được retransform |

Một điều đặc biệt dễ gây hiểu nhầm: **`redefineClasses` không “bỏ qua các transformer”.** `ClassFileTransformer` được gọi khi class được load, **khi class được redefine**, và khi class được retransform nếu transformer đã đăng ký `canRetransform=true`. Vì thế nếu bạn cung cấp replacement bytes mà một transformer khác tự động chỉnh lại, class hiệu lực có thể khác đúng bytes trong tệp nguồn. Đó không phải bug của `redefineClasses`; đó là cơ chế pipeline.

### 3.1. Các lời gọi dạng tối giản

**Redefinition** — caller có byte[] của **toàn bộ classfile**:

~~~java
Class<?> target = /* Class<?> đúng loader đã nạp */;
byte[] replacement = /* toàn bộ .class mới hợp lệ */;

instrumentation.redefineClasses(
    new ClassDefinition(target, replacement)
);
~~~

**Retransformation** — caller yêu cầu JVM chạy lại transformer:

~~~java
Class<?> target = /* Class<?> đúng loader đã nạp */;
instrumentation.retransformClasses(target);
~~~

Đây là **đoạn mã minh họa API**, không phải hai chương trình độc lập: các biến `instrumentation`, `target`, `replacement` cần được lấy trong một agent thực. Ví dụ hoàn chỉnh phía dưới triển khai đủ class, đường dẫn và lệnh build.

## 4. Nguồn bytes khi `retransformClasses`: lịch sử lần load và lần redefine

Cần hiểu chính xác từ “initial class file bytes” trong Javadoc. Nó không có nghĩa “luôn là tệp JAR đầu tiên ứng dụng từng đọc”. Sau một lần redefine, **nguồn cơ sở của các lần retransform kế tiếp được thiết lập từ định nghĩa mới**.

Hình dung trình tự với một method `Message.text()`:

~~~text
A. JVM load Message.class ban đầu:
   base bytes chứa "BASE"
   -> (không transformer nào sửa) -> text() trả "BASE"

B. Transformer capable được bật; gọi retransformClasses(Message.class):
   JVM dựa trên base bytes "BASE"
   -> transformer đổi "BASE" thành "LIVE"
   -> text() trả "LIVE"

C. Tắt phép biến đổi rồi retransformClasses(Message.class) lần nữa:
   JVM vẫn dựa trên base bytes "BASE"
   -> transformer trả null
   -> text() trở lại "BASE" (trong ví dụ chỉ có 1 transformer capable)

D. Caller có classfile biên dịch lại chứa "EDIT"; gọi redefineClasses:
   bytes "EDIT" -> transformer lúc này không sửa -> text() trả "EDIT"
   LẦN REDEFINE NÀY tạo nguồn cơ sở mới

E. Bật transformer rồi gọi retransformClasses:
   JVM dựa trên nguồn cơ sở "EDIT" của lần redefine gần nhất
   -> transformer đổi "EDIT" thành "PIPE"
   -> text() trả "PIPE"

F. Tắt transformer rồi retransformClasses lần nữa:
   JVM dựa trên nguồn cơ sở "EDIT"
   -> transformer trả null
   -> text() trở lại "EDIT", không phải "BASE"
~~~

Chính vì vậy, **retransform không phải nút “khôi phục về phiên bản JAR lúc JVM khởi động”**. Nó chạy lại pipeline trên **cơ sở hiện hành do JVM giữ**. Nếu muốn quay lại mã `"BASE"` sau khi đã redefine sang `"EDIT"`, bạn thường cần cung cấp lại **classfile bytes BASE** bằng một lần `redefineClasses` mới (khi các ràng buộc cho phép), hoặc thiết kế một transformer tạo bytes tương ứng. Không suy ra cách rollback chỉ từ việc bật/tắt một cờ.

### 4.1. Các transformer không retransform-capable có biến mất không?

**Không.** Theo Javadoc, trong lượt `retransformClasses`:

- Với mỗi transformer đăng ký `canRetransform=false`, JVM **không gọi lại callback** mà **tái áp dụng kết quả transform của lần class load hoặc redefine gần nhất**.
- Với transformer `canRetransform=true`, JVM **gọi lại `transform(...)`** để tạo output hiện tại.
- Thứ tự nhóm transform được giữ theo hợp đồng, gồm các nhóm Java/native capable và incapable.

Vì vậy “tắt transformer capable rồi retransform trả về base bytes” chỉ đúng trong bối cảnh không còn biến đổi khác có hiệu lực. Nếu các agent khác đã instrument class hoặc transformer không capable từng tạo mã, kết quả sau khi tắt một transformer có thể vẫn chứa instrumentation của agent khác.

### 4.2. Bytes của `redefineClasses` vẫn đi qua pipeline

Nguồn cơ sở của redefine là `ClassDefinition.getDefinitionClassFile()`; trước khi cài đặt, JVM có thể áp dụng những transformer đã đăng ký. Điều này có hai hệ quả:

1. Tệp `.class` bạn cung cấp phải đúng class, version, schema trước cả khi transformation. Nếu transformer biến đổi nó, **output cuối** cũng phải hợp lệ.
2. Nếu công cụ lấy bytes hiện hành **đã bị transformer sửa** rồi lại đưa chúng làm replacement bytes, một transformer có thể áp dụng lại và gây **double instrumentation**. Đừng dùng “bytes nhìn thấy sau instrument” như thể đó là nguồn classfile sạch trừ khi thiết kế pipeline đã xử lý khả năng lặp.

Khi nhiều agent cùng can thiệp, nên mô hình hóa rõ **owner** của source-of-truth bytes, thứ tự transformer, marker idempotency và hành vi khi transformer bị remove.

## 5. Bốn điều kiện trước khi sửa class đã nạp

### 5.1. Capability là tùy chọn, và hai cờ độc lập

Đối với startup agent cần cả hai tính năng, manifest main section:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SwitchAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Với agent nạp động qua Attach API, dùng `Agent-Class`/`agentmain` và khai báo `Can-*` tương ứng. Một agent có thể chỉ xin `Can-Redefine-Classes` hoặc chỉ xin `Can-Retransform-Classes` khi không cần tính năng kia.

Sau đó **phải đọc runtime**:

~~~java
boolean canRedefine = instrumentation.isRedefineClassesSupported();
boolean canRetransform = instrumentation.isRetransformClassesSupported();
~~~

Hai kết quả này không thay thế nhau. Manifest yêu cầu `true` mới là **điều kiện cần**, JVM/cấu hình hiện tại vẫn có thể không cung cấp capability. Đừng suy từ “JDK 17” hoặc từ vendor máy developer mà khẳng định mọi JVM trên production trả cùng giá trị.

### 5.2. Modifiability là điều kiện của từng class

~~~java
if (!instrumentation.isModifiableClass(targetClass)) {
    throw new IllegalArgumentException("Class is not modifiable");
}
~~~

Ngay cả khi cả hai capability toàn JVM đều `true`, một `Class<?>` cụ thể có thể không modifiable. Primitive và array classes không thể sửa; có thể có những loại class khác cũng bị JVM từ chối. Kết quả `isModifiableClass` **độc lập** với hai capability flags và không bảo đảm mọi thay đổi của class đều hợp lệ.

### 5.3. Class identity gồm cả defining loader

Đối với plugin architecture:

~~~text
pluginLoaderA -> com.shop.Cart  // class A
pluginLoaderB -> com.shop.Cart  // class B
~~~

Hai tên giống nhau nhưng hai `Class<?>` **khác nhau**. `redefineClasses` yêu cầu đúng class object và full bytes có **binary name phù hợp**. `retransformClasses` cũng nhận đúng class object; không thể chỉ truyền chuỗi `"com.shop.Cart"`.

Nếu dùng `getAllLoadedClasses()` để tìm class:

~~~java
for (Class<?> c : instrumentation.getAllLoadedClasses()) {
    if ("com.shop.Cart".equals(c.getName())
            && c.getClassLoader() == expectedLoader) {
        // c là candidate, còn phải kiểm tra modifiability.
    }
}
~~~

Đoạn này chỉ minh họa; `expectedLoader` phải được xác định theo kiến trúc thật. Không gọi `Class.forName(...)` tùy tiện để “tìm” một class đã load, vì hành động đó có thể tạo lần định nghĩa mới ở một loader khác.

### 5.4. Classfile hợp lệ và trong giới hạn JVM TI

Cả hai cơ chế đều không phải class schema migration. Theo giới hạn của nhiều JVM, các thay đổi sau bị từ chối:

- Thêm, xóa hoặc đổi tên field/method.
- Đổi inheritance/interfaces.
- Thay đổi những thuộc tính method/class mà JVM TI không hỗ trợ đổi.
- Cung cấp classfile version không được runtime chấp nhận.
- Cung cấp bytes không khớp binary name của `targetClass`.
- Sinh StackMapTable, constant pool, bytecode, verifier state hoặc helper visibility sai.

Thay đổi **method body** là trường hợp phù hợp nhất để bắt đầu. Với những VM/JDK đặc thù có hỗ trợ mở rộng, phải kiểm tra theo đúng implementation; **không mặc nhiên** coi cả hai API là cơ chế thay class tuỳ ý.

## 6. Quy trình quyết định thực tế

Sử dụng cây quyết định trước khi viết code:

~~~text
Bạn muốn sửa một class đã nạp?
|
+-- Không, class chưa load
|     -> Đăng ký ClassFileTransformer để xử lý initial class definition.
|
+-- Có
      |
      +-- Bạn có full replacement .class bytes đáng tin, đã build sẵn?
      |      |
      |      +-- Có: mục tiêu hot-fix / đổi method body từ bản biên dịch mới?
      |              -> Ưu tiên cân nhắc redefineClasses(...)
      |                 check Can-Redefine-Classes + isRedefineClassesSupported
      |
      +-- Bạn muốn chạy lại bytecode transformation logic hiện có?
      |      |
      |      +-- Có: bật/tắt/thay chính sách instrumentation
      |              -> Ưu tiên cân nhắc retransformClasses(...)
      |                 check Can-Retransform-Classes + isRetransformClassesSupported
      |
      +-- Bạn muốn đổi schema: thêm field, thay superclass, v.v.?
             -> Thiết kế thay thế; đừng chọn một trong hai với hy vọng lách giới hạn.

Sau khi chọn:
   đúng Class<?>/loader?
   class modifiable?
   source bytes hiện hành có đúng?
   transformer pipeline có thể tác động?
   bytecode mới hợp lệ?
   active frames/static state có ảnh hưởng?
   test + rollback plan?
~~~

### Các ví dụ cụ thể

**A. Hotfix logic tính phí từ bản build mới.** CI tạo `BillingService.class` đã ký/được xác thực và chứa method body sửa bug, cùng class name/schema như class đang chạy. Nếu mục tiêu là **lấy bản build ấy làm định nghĩa cơ sở mới**, `redefineClasses` diễn đạt đúng ý định hơn. Dù vậy phải kiểm tra tương thích state, constant pool, classfile version và các transformers có thể chạy trên bytes đó.

**B. Agent tracing đã attach, muốn instrument các lớp đã load.** Không có sẵn `.class` thay thế; agent có transformer biết chèn timing hooks vào đầu/cuối method. Đăng ký `addTransformer(transformer, true)` rồi gọi `retransformClasses(selectedClasses)` sau khi kiểm tra. Đây là use case tự nhiên của retransform.

**C. Thay bộ lọc hoặc cấu hình sampling của agent.** Nếu transformer đọc cấu hình bất biến mới hoặc có thể được bật/tắt an toàn và muốn cập nhật những lớp đang chạy, gọi `retransformClasses` với class set được chọn. Nếu công cụ đã tính full replacement bytes bên ngoài pipeline, có thể cân nhắc redefine, nhưng phải lưu ý transformer vẫn được gọi.

**D. Debugger fix-and-continue.** IDE có classfile vừa biên dịch cho một method và muốn thay định nghĩa runtime. `redefineClasses` là trường hợp được Javadoc `Instrumentation` gợi ý rõ. Cập nhật source bên ngoài JVM **không** làm class đã load tự đổi; cần thao tác explicit.

**E. Khôi phục trước khi có instrumentation.** Nếu chỉ transformer capable của bạn đã sửa bytes và nguồn cơ sở không thay, tắt transformer rồi retransform có thể trở lại cơ sở. Nếu đã redefine sang bytes khác, retransform sẽ dựa vào định nghĩa mới; muốn quay lại bản cũ cần quản lý **snapshot bytes/phiên bản** thật sự và áp dụng quy trình rollback thích hợp.

**F. Tạo class mới với field mới.** Nếu nghiệp vụ cần thay cấu trúc object, cả hai cơ chế không phải công cụ migration tổng quát. Một ứng dụng có thể phải khởi động lại, dùng versioned classes/loaders, chuyển state qua schema khác hoặc đặt dữ liệu bổ sung ở external map với cleanup đúng.

## 7. Demo Java 17+: nhìn thấy hai nguồn bytes thay đổi theo thời gian

Bài thực hành bên dưới dùng **startup agent** để đơn giản hóa việc giữ cùng `Instrumentation` và cùng transformer trong một JVM. Vẫn áp dụng cùng nguyên tắc cho `agentmain` khi Attach, nhưng Attach có thêm yêu cầu về quyền/process và chính sách dynamic agent loading.

Demo có:

- `demo.Message` ban đầu do `javac` biên dịch với `text() -> "BASE"`.
- Một `demo.Message` thay thế từ source khác, cùng binary name, signature và class schema, nhưng `text() -> "EDIT"`.
- `SwitchAgent` đăng ký **một** `ClassFileTransformer` capable. Khi bật, transformer đổi đúng constant-pool UTF8 ASCII `"BASE"` thành `"LIVE"` hoặc `"EDIT"` thành `"PIPE"`. Chúng đều dài **4 byte**, nên demo không thay đổi bố cục classfile.
- `App` gọi cả `retransformClasses` và `redefineClasses`, in kết quả sau mỗi bước.

**Cảnh báo quan trọng:** viết tay parser constant pool và đổi literal là **thủ thuật minh họa nhỏ**, không phải giải pháp instrument sản phẩm. Nó chỉ làm việc với đúng hai class demo chứa literal ASCII bốn byte, không tạo/chèn instruction, không hỗ trợ classfile tùy ý. Khi cần thay method body có cấu trúc, hãy dùng thư viện như ASM/Byte Buddy trên JDK 17, hoặc Class-File API chuẩn từ JDK 24 nếu target phù hợp.

### 7.1. Thư mục dự án

~~~text
redefine-vs-retransform/
├── AGENT.MF
├── src/
│   ├── base/demo/Message.java
│   ├── edited/demo/Message.java
│   ├── agent/demo/agent/SwitchAgent.java
│   └── app/demo/App.java
└── out/                         # Tạo trong bước build
    ├── base/demo/Message.class
    ├── edited/demo/Message.class
    ├── agent/
    ├── app/
    └── switch-agent.jar
~~~

Hai tệp `src/base/demo/Message.java` và `src/edited/demo/Message.java` có **cùng package, tên class và tên tệp** nhưng được biên dịch vào **hai output directories khác nhau**. Tuyệt đối không thêm **cả hai thư mục** vào runtime classpath khi chạy demo; runtime dùng `out/base`, còn `out/edited` chỉ cung cấp classfile bytes cho `redefineClasses`.

### 7.2. Tệp `src/base/demo/Message.java`

~~~java
package demo;

public final class Message {
    private Message() {}

    public static String text() {
        return "BASE";
    }
}
~~~

### 7.3. Tệp `src/edited/demo/Message.java`

~~~java
package demo;

public final class Message {
    private Message() {}

    public static String text() {
        return "EDIT";
    }
}
~~~

Chúng có cùng `demo.Message`, cùng method `text()Ljava/lang/String;`, cùng modifiers và cùng class hierarchy. Chỉ literal trả về trong method body thay đổi. Trên JVM thông thường có hỗ trợ redefine, đây là kiểu thay đổi phù hợp để thử.

### 7.4. Tệp `src/agent/demo/agent/SwitchAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class SwitchAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile boolean patchEnabled;

    private SwitchAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;

        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();

        System.out.println("[agent] capabilities retransform="
                + canRetransform + " redefine=" + canRedefine);

        if (!canRetransform || !canRedefine) {
            throw new IllegalStateException(
                    "Both capabilities required for this demo");
        }

        // Transformer được đăng ký từ startup, nhưng ban đầu chưa patch.
        inst.addTransformer(new LiteralPatchTransformer(), true);
    }

    public static void retransform(Class<?> target, boolean enablePatch)
            throws UnmodifiableClassException {

        Instrumentation inst = requireInstrumentation();
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Retransformation unavailable for target");
        }

        patchEnabled = enablePatch;
        inst.retransformClasses(target);
    }

    public static void redefine(Class<?> target, Path replacementFile)
            throws Exception {

        Instrumentation inst = requireInstrumentation();
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Redefinition unavailable for target");
        }

        // Ngừng patch để bytes EDIT do caller cung cấp được sử dụng.
        patchEnabled = false;

        byte[] newClassFile = Files.readAllBytes(replacementFile);
        inst.redefineClasses(new ClassDefinition(target, newClassFile));
    }

    private static Instrumentation requireInstrumentation() {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Run this app with -javaagent");
        }
        return inst;
    }

    private static final class LiteralPatchTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] bytes) {

            if (!patchEnabled
                    || !"demo/Message".equals(className)
                    || loader != ClassLoader.getSystemClassLoader()) {
                return null;
            }

            byte[] changed = replaceSingleLiteral(bytes);
            if (changed != null) {
                System.out.println(
                        "[agent] transformer patched demo.Message");
            }
            return changed;
        }

        // Parser constant pool TỐI GIẢN chỉ để minh họa.
        // Không dùng cho classfile bất kỳ từ nguồn không tin cậy.
        private static byte[] replaceSingleLiteral(byte[] original) {
            if (original.length < 10
                    || (original[0] & 255) != 0xCA
                    || (original[1] & 255) != 0xFE
                    || (original[2] & 255) != 0xBA
                    || (original[3] & 255) != 0xBE) {
                return null;
            }

            byte[] copy = original.clone();
            int cpCount = u2(original, 8);
            int offset = 10;
            int replacements = 0;

            for (int index = 1; index < cpCount; index++) {
                if (offset >= original.length) {
                    return null;
                }

                int tag = original[offset++] & 255;
                switch (tag) {
                    case 1: { // CONSTANT_Utf8
                        if (offset + 2 > original.length) {
                            return null;
                        }
                        int length = u2(original, offset);
                        offset += 2;
                        if (offset + length > original.length) {
                            return null;
                        }

                        if (length == 4) {
                            if (isAscii(original, offset, "BASE")) {
                                putAscii(copy, offset, "LIVE");
                                replacements++;
                            } else if (isAscii(original, offset, "EDIT")) {
                                putAscii(copy, offset, "PIPE");
                                replacements++;
                            }
                        }
                        offset += length;
                        break;
                    }
                    case 3: case 4:
                    case 9: case 10: case 11: case 12:
                    case 17: case 18:
                        offset += 4;
                        break;
                    case 5: case 6:
                        offset += 8;
                        index++; // long/double dùng hai CP slots.
                        break;
                    case 7: case 8: case 16:
                    case 19: case 20:
                        offset += 2;
                        break;
                    case 15:
                        offset += 3;
                        break;
                    default:
                        return null;
                }

                if (offset > original.length) {
                    return null;
                }
            }
            return replacements == 1 ? copy : null;
        }

        private static int u2(byte[] bytes, int offset) {
            return ((bytes[offset] & 255) << 8)
                    | (bytes[offset + 1] & 255);
        }

        private static boolean isAscii(
                byte[] bytes, int offset, String literal) {
            for (int i = 0; i < literal.length(); i++) {
                if ((bytes[offset + i] & 255) != literal.charAt(i)) {
                    return false;
                }
            }
            return true;
        }

        private static void putAscii(
                byte[] bytes, int offset, String literal) {
            for (int i = 0; i < literal.length(); i++) {
                bytes[offset + i] = (byte) literal.charAt(i);
            }
        }
    }
}
~~~

**Giải thích quan trọng về transformer:**

- `patchEnabled` ban đầu `false`, nên lần JVM định nghĩa `demo.Message` ban đầu không bị thay.
- Khi gọi `retransform(..., true)`, JVM gọi lại `transform` vì đăng ký `canRetransform=true`. Transformer không sửa byte array đầu vào in-place mà `clone()` rồi trả bytes mới.
- Hàm `replaceSingleLiteral` chỉ đổi một `CONSTANT_Utf8` dài 4 có value `BASE` hoặc `EDIT`. Nó không parse/đổi method structure; string literal trong `Message.text()` được tham chiếu qua `CONSTANT_String` tới UTF8. Phép sửa này có tác dụng với hai class do ví dụ cung cấp, không chứng minh mọi constant pool modification đều an toàn.
- Khi `patchEnabled=false`, transformer trả `null`. Với demo chỉ có một transformer capable, retransform lại sẽ lấy bytes cơ sở chưa bị patch bởi transformer đó, cho phép quan sát sự khác biệt giữa **BASE trước redefine** và **EDIT sau redefine**.
- `redefine(...)` tạo `ClassDefinition` từ bytes của tệp **replacement** và tạm tắt patch. Nhưng về nguyên tắc pipeline vẫn được gọi trên redefine; việc không sửa là do chính transformer của demo trả `null`.
- Nếu classfile không có chính xác một literal đích, parser trả `null` (bỏ qua), không thử biến đổi mù. Đây chỉ là bài thực hành; production cần parser classfile thực sự, logging an toàn và quản lý đồng thời.

**Tại sao cần `volatile`?** Một Java agent thực có thể nhận callbacks từ các thread nạp class khác nhau. `volatile` đảm bảo giá trị cờ có cơ chế visibility căn bản. Demo gọi thao tác tuần tự; nếu sản phẩm hỗ trợ nhiều yêu cầu đồng thời, một cờ global vẫn **chưa đủ** để bảo đảm từng thao tác dùng đúng cấu hình và cần một thiết kế đồng bộ/immutable config thích hợp.

### 7.5. Tệp `src/app/demo/App.java`

~~~java
package demo;

import demo.agent.SwitchAgent;
import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: demo.App <replacement-class-file>");
        }

        // Bắt đầu với bytes từ out/base/demo/Message.class.
        System.out.println("initial=" + Message.text());

        // retransform lấy base bytes BASE, transformer đổi thành LIVE.
        SwitchAgent.retransform(Message.class, true);
        System.out.println("after retransform=" + Message.text());

        // Tắt transformer, retransform chạy lại từ BASE.
        SwitchAgent.retransform(Message.class, false);
        System.out.println("after retransform off=" + Message.text());

        // Thay cơ sở bằng full replacement .class chứa EDIT.
        SwitchAgent.redefine(Message.class, Path.of(args[0]));
        System.out.println("after redefine=" + Message.text());

        // Giờ retransform bắt đầu từ EDIT, không từ BASE.
        SwitchAgent.retransform(Message.class, true);
        System.out.println(
                "after retransform since redefine=" + Message.text());

        // Tắt patch; nguồn cơ sở mới vẫn là EDIT.
        SwitchAgent.retransform(Message.class, false);
        System.out.println(
                "after retransform off since redefine=" + Message.text());
    }
}
~~~

Cần chú ý rằng `App` gọi `Message.text()` lần đầu **trước khi** yêu cầu retransform hoặc redefine, nên class đã được nạp. Không có nhu cầu dùng Attach API cho bài demo này: startup agent cung cấp `Instrumentation` sẵn sàng, còn chương trình chủ động chọn thời điểm từng thao tác.

### 7.6. Tệp `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SwitchAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Hai flag là cần thiết vì demo dùng **cả hai** API. Đối với một agent chỉ cần redefine, không nên xin retransform một cách máy móc. Tệp manifest phải có newline kết thúc; `jar cfm` sẽ đưa vào `META-INF/MANIFEST.MF`.

### 7.7. Biên dịch và đóng gói với JDK 17+

Tạo thư mục output từ root `redefine-vs-retransform`.

**Trên Bash:**

~~~bash
mkdir -p out/base out/edited out/agent out/app
~~~

**Trên PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/base, out/edited, out/agent, out/app | Out-Null
~~~

Biên dịch hai class cùng tên vào **hai thư mục riêng**; biên dịch agent; tạo agent JAR:

~~~bash
javac --release 17 -d out/base src/base/demo/Message.java

javac --release 17 -d out/edited src/edited/demo/Message.java

javac --release 17 -d out/agent src/agent/demo/agent/SwitchAgent.java

jar cfm out/switch-agent.jar AGENT.MF -C out/agent .
~~~

Để biên dịch `App`, classpath phải có **bản BASE** và agent JAR vì source `App` trực tiếp gọi `SwitchAgent`.

**Bash/Linux/macOS:**

~~~bash
javac --release 17 -cp "out/base:out/switch-agent.jar" -d out/app src/app/demo/App.java
~~~

**Windows PowerShell hoặc CMD:**

~~~powershell
javac --release 17 -cp "out/base;out/switch-agent.jar" -d out/app src/app/demo/App.java
~~~

Khi chạy, **không** đưa `out/edited` vào classpath. File EDIT được truyền bằng **đường dẫn tới tệp `.class`**, không được loader nạp từ đầu.

### 7.8. Chạy và stdout dự kiến

**Bash/Linux/macOS:**

~~~bash
java -javaagent:out/switch-agent.jar -cp "out/app:out/base:out/switch-agent.jar" demo.App out/edited/demo/Message.class
~~~

**Windows:**

~~~powershell
java -javaagent:out/switch-agent.jar -cp "out/app;out/base;out/switch-agent.jar" demo.App out/edited/demo/Message.class
~~~

Trên **HotSpot JDK 17+ thông thường hỗ trợ cả hai capability** và chạy đúng mã nguồn demo, stdout dự kiến:

~~~text
[agent] capabilities retransform=true redefine=true
initial=BASE
[agent] transformer patched demo.Message
after retransform=LIVE
after retransform off=BASE
after redefine=EDIT
[agent] transformer patched demo.Message
after retransform since redefine=PIPE
after retransform off since redefine=EDIT
~~~

Bản nào không hỗ trợ cả hai capability sẽ **không** có stdout trên: `premain` chủ động fail-fast vì demo cần cả hai. Điều đó không chứng minh JDK không có Instrumentation API; nó chỉ chứng minh runtime hiện tại không có đủ tính năng demo yêu cầu.

**Phân tích từng chuyển trạng thái:**

| Mốc | Thao tác | Nguồn bytes | Transformer active? | Kết quả method |
|---|---|---|---|---|
| 1 | Initial class load | BASE từ `out/base` | Không | `BASE` |
| 2 | `retransformClasses` | BASE từ JVM | Có; `BASE → LIVE` | `LIVE` |
| 3 | `retransformClasses` | Vẫn BASE từ JVM | Không | `BASE` |
| 4 | `redefineClasses(ClassDefinition(EDIT bytes))` | **EDIT bytes từ file mới** | Không | `EDIT` |
| 5 | `retransformClasses` | **EDIT từ lần redefine gần nhất** | Có; `EDIT → PIPE` | `PIPE` |
| 6 | `retransformClasses` | Vẫn EDIT từ lần redefine | Không | `EDIT` |

Dòng quan trọng nhất là bước 6: sau khi redefine, tắt transformer và retransform **không quay về `BASE`**, mà quay về `EDIT`, vì lần redefine đã thay đổi nguồn cơ sở. Đây chính là ý nghĩa “chọn theo nguồn byte”.

Để kiểm tra hiệu quả của việc chuẩn bị đúng bytes thay thế, hãy bảo đảm `out/base/demo/Message.class` và `out/edited/demo/Message.class` đều tồn tại, nhưng chỉ `out/base` nằm trên runtime classpath. Khi gọi `redefineClasses`, caller nạp **bytes của file EDIT**, không nhờ class loader define thêm một bản class thứ hai.

### 7.9. Những gì demo không chứng minh

- Việc đổi literal UTF8 trong constant pool là thủ thuật an toàn **chỉ cho dữ liệu demo cụ thể**; không dùng parser này để chỉnh classfile tùy ý hoặc production.
- Nó không thêm field/method mới và không vượt các giới hạn schema.
- Nó không minh họa trạng thái active frames. Method `text()` kết thúc rất nhanh; các lần gọi sau thay definition dùng definition mới.
- Demo chỉ có **một Java transformer capable**; nhiều agent/native transformers và các nhóm incapable có thể tạo output khác.
- Demo cố ý dùng startup agent, không kiểm thử dynamic Attach policy; khi chuyển sang Attach cần `Agent-Class`/`agentmain`, quyền attach, cách tìm đúng `Class<?>` đã nạp và cấu hình JVM thích hợp.

## 8. Phân biệt “nguồn bytes” với “mục tiêu thay đổi”

Nhiều sai lầm xuất hiện vì công cụ chỉ hỏi “muốn đổi behavior không?” mà không hỏi **ai sở hữu source of truth**.

### 8.1. Khi bạn có tệp classfile biên dịch lại

`redefineClasses` phù hợp hơn nếu bạn muốn **đưa một phiên bản classfile bên ngoài làm cơ sở mới**. Nó dễ dùng trong IDE hot-swap, live patch, debugging có build artefact đã ký.

Nhưng phải làm rõ:

- Bytes ấy đến từ **đúng build**, đúng class name, đúng target Java version và schema.
- Class đang chạy nằm trong loader/module nào; không được gửi nhầm class của một plugin khác.
- Transformer khác đang được đăng ký có thể tự áp dụng trên những bytes này khi redefine.
- Bytecode mới có đọc state cũ theo assumption mới không? Không có chuyện tự migrate static fields hoặc object instances.
- Có bản snapshot classfile cũ đã xác thực để rollback bằng một lượt redefine khác không?

Khi hotfix là bản class chứa method body sửa logic, cần kiểm tra patch có phụ thuộc việc thêm field mới hoặc đổi constructor/superclass không. Những thay đổi ấy có thể không được hỗ trợ dù biên dịch source mới hoàn toàn hợp lệ.

### 8.2. Khi bạn có một thuật toán transform, không có tệp thay thế

`retransformClasses` phù hợp nếu logic của bạn là “với định nghĩa của class đang có, hãy áp dụng lại quy tắc chèn bytecode của agent”. Điển hình:

- Thêm/bỏ hooks tracing cho method có annotation cụ thể.
- Thay chính sách coverage hoặc security monitoring trong lớp đã load.
- Bật lại transformer sau khi attach muộn.
- Cập nhật instrumentation rules khi một feature được bật/tắt.

Điều quan trọng là transformer phải **idempotent** theo nguồn đầu vào và chuỗi transformer, không nhân đôi instrumentation khi retransform lặp. Nếu dùng nhiều transformers, xem cách JVM tái áp dụng kết quả của những transformer `canRetransform=false`.

### 8.3. Khi thuật toán transform dùng bytes từ bên ngoài

Một `ClassFileTransformer` có thể về mặt kỹ thuật **trả cả classfile bytes mới** mà nó đọc từ nơi khác. Do đó “retransform nghĩa là không bao giờ dùng external bytes” là cách giải thích quá tuyệt đối.

Đúng hơn:

- **API retransform không nhận full classfile bytes từ caller**; JVM chọn nguồn đầu vào và gọi pipeline.
- **Transformer** có thể quyết định dùng nguồn dữ liệu khác để tạo output, miễn classfile hợp lệ và đáp ứng giới hạn.
- Nếu nguồn dữ liệu chủ đạo là một **bản .class thay thế đã chuẩn bị sẵn**, `redefineClasses` thường thể hiện ý định rõ hơn, ít tạo phụ thuộc không cần thiết vào transformer callback.
- Trong cả hai trường hợp, phải xác định trách nhiệm về versioning, integrity và compatibility.

### 8.4. Khi chỉ muốn class mới được instrument

Nếu class **chưa được nạp**, không có `Class<?>` để gọi `retransformClasses`/`redefineClasses` theo nghĩa thay một class đã tồn tại. Đăng ký `ClassFileTransformer` trước lần class definition và transform ở load-time là workflow phù hợp.

Không gọi `Class.forName` chỉ để lấy class object rồi “retransform” nếu mục tiêu là chặn **lần load đầu tiên**: việc tìm class có thể kích hoạt load quá sớm, làm bỏ lỡ điểm instrumentation dễ nhất.

## 9. Giới hạn runtime chung: không phải restart hay schema migration

### 9.1. Active stack frames

Theo Javadoc của cả hai API, nếu một method đang có **active frames** lúc class được thay:

- Các frame hiện tại có thể tiếp tục thực thi **bytecode của version cũ**.
- Các lần invoke mới sau khi thay thành công sẽ dùng định nghĩa mới.

Hãy thiết kế test có phương thức chạy lâu, đồng bộ trước khi swap và kiểm tra hai nhóm lời gọi. Không xem một stack frame còn in giá trị cũ là bằng chứng redefine/retransform thất bại.

### 9.2. Static state và instances

Không API nào tự chạy lại `<clinit>` hay reset các static fields đã có. Objects hiện tồn tại cũng không bị dựng lại. Hậu quả thực tế:

- Method body mới sử dụng giá trị static hiện hành, không phải static initializer từ bản source mới vừa biên dịch.
- Nếu source mới “mong” có thêm field, class schema có thể bị từ chối, hoặc thiết kế cần external state.
- Nếu logic mới giả định invariant khác cho instance cũ, phải có kế hoạch tương thích state; API không tự sửa invariant đó.

### 9.3. Lệnh retransform/redefine trên một nhóm class

Cả hai API nhận **nhiều class** trong một lần gọi; JVM kiểm tra và cài đặt như một thao tác nhóm theo contract: nếu có lỗi, **không class nào trong lượt đó được thay**. Điều đó không có nghĩa nhiều lần gọi riêng lẻ là một transaction: nếu bạn chạy 3 lời gọi độc lập và lời gọi thứ 3 thất bại, những lời gọi trước đã hoàn tất không tự rollback.

Vì thế với thay đổi liên quan nhiều class, cân nhắc một lượt trên một nhóm class phù hợp. Nhưng batch càng lớn càng tăng chi phí và nguy cơ gặp một target không modifiable. Phải lựa chọn nhóm dựa trên phụ thuộc thực tế.

### 9.4. Quyền, module và helper visibility

Transformer tạo bytes gọi helper trong agent cần xem:

- Defining loader của target có nhìn thấy helper không?
- Module đích có đủ readability/exports/opens cần thiết không?
- Helper được thêm vào bootstrap hoặc system search path đã đúng thời điểm chưa?
- Method signature và class version có tương thích runtime không?

`Instrumentation.redefineModule(...)` có thể mở rộng một số quan hệ module khi cần và được phép; nó là **bài toán khác** với chọn redefine/retransform. Không “mở tất cả packages” để chữa mọi lỗi linking.

## 10. Exception và chế độ thất bại

Các thao tác có thể ném các lỗi khác nhau, chẳng hạn:

| Nhóm vấn đề | Ví dụ | Cách phản ứng phù hợp |
|---|---|---|
| JVM không cấp capability | `UnsupportedOperationException` khi yêu cầu feature không được hỗ trợ | Kiểm tra `is...Supported()`, chọn fallback hoặc fail-fast rõ ràng |
| Target không modifiable | `UnmodifiableClassException` | Skip target và báo lý do, không retry vô hạn |
| Bytes của redefine sai tên | `NoClassDefFoundError` | So khớp tên classfile với `targetClass` và đúng loader |
| Classfile sai định dạng | `ClassFormatError` | Kiểm tra parser/writer, verifier, nguồn bytes |
| Classfile version không tương thích | `UnsupportedClassVersionError` | Biên dịch đúng target Java version |
| Thay schema không được hỗ trợ | `UnsupportedOperationException` | Thiết kế patch chỉ sửa method body hoặc dùng kiến trúc khác |
| Thất bại liên kết/verifier | `LinkageError`, `VerifyError` và lỗi liên quan | Đối chiếu stack map, constant pool, hierarchy và helper visibility |
| Đọc file replacement thất bại | `IOException` bên phía công cụ | Không gọi redefine với dữ liệu rỗng/không đầy đủ |
| Rủi ro do agent can thiệp | Chưa crash nhưng behavior sai | Test runtime, metric, rollback dựa trên source bytes đã lưu |

**Một ngoại lệ của `retransformClasses`/`redefineClasses` có nghĩa lượt yêu cầu đó thất bại**, không được giả định target class đã bị thay một phần. Tuy nhiên nếu quá trình chuẩn bị bên ngoài (ghi file, nạp agent khác, sửa cấu hình) đã xảy ra thì API không tự rollback những side effects bên ngoài ấy.

Đối với transformer, một callback ném exception có thể được JVM xử lý theo hợp đồng cho phép pipeline tiếp tục; **đừng lạm dụng exception như công cụ chặn mọi class definition**. Công cụ cần kiểm tra kết quả và log đúng lớp lỗi.

### 10.1. Fail-fast hay degrade?

- Nếu công cụ chỉ thu metric và có thể mất vài target, thiếu capability có thể degrade thành load-time-only hoặc skip target với thông báo.
- Nếu patch để sửa lỗi nghiệp vụ **bắt buộc** phải được cài đặt thì thiếu capability hoặc class không modifiable nên là lỗi chặn triển khai, không được in “Patch applied”.
- Nếu patch cần đồng nhất nhiều class, một yêu cầu nhóm và kiểm thử phụ thuộc tốt hơn việc chắp vá tuần tự không có kiểm soát.

Không nên in `"class changed"` ngay khi `addTransformer` trả về; phương thức đó chỉ đăng ký callback. Chỉ sau khi thao tác thành công và **hành vi đã được xác minh** mới coi bản sửa đạt mục tiêu.

## 11. Lỗi thiết kế thường gặp

### Lỗi 1 — “Redefine là retransform với bytes mới”

Chưa đúng. `redefineClasses` nhận **full bytes từ caller**, `retransformClasses` nhận **class objects** rồi chạy pipeline với bytes cơ sở JVM quản lý. Sau một lần redefine, cơ sở của các lần retransform có thể thay đổi.

### Lỗi 2 — “Redefine bỏ qua mọi transformer”

Sai. Transformer được gọi trên các lượt **class redefinition** theo contract. Một agent khác có thể tiếp tục sửa bytes mà bạn vừa cung cấp. Cần xem toàn bộ pipeline khi chẩn đoán output không khớp replacement file.

### Lỗi 3 — “retransform sau redefine sẽ quay về bản JAR ban đầu”

Sai. Định nghĩa cơ sở cho retransform sau đó đến từ **lần redefine gần nhất** (trong demo là EDIT). Nếu cần quay lại BASE phải khôi phục source bytes phù hợp, không chỉ tắt transformer.

### Lỗi 4 — “canRetransform=false sẽ được gọi lại khi retransform”

Sai. JVM tái dùng tác động trước của transformer `canRetransform=false`; chỉ nhóm capable được callback lại. Một callback không được gọi lại không đồng nghĩa tác động cũ của nó đã biến mất.

### Lỗi 5 — “Cứ đổi schema bằng một trong hai API sẽ được”

Sai. Những thay đổi như thêm/xóa field, thay method signature hay inheritance bị hạn chế; nhiều JVM từ chối. Muốn migration state/object layout thường cần phương án kiến trúc khác.

### Lỗi 6 — “Capability retransform đồng nghĩa có capability redefine”

Sai. `Can-Retransform-Classes` và `Can-Redefine-Classes` là hai thuộc tính tùy chọn khác nhau; phải kiểm tra hai truy vấn tương ứng trước từng API.

### Lỗi 7 — “Có thể redefine class theo tên string”

Sai. Cả hai API đòi **`Class<?>` đúng JVM runtime type**. Hai loader khác nhau có thể định nghĩa cùng binary name nhưng đó là hai class khác identity.

### Lỗi 8 — “Class có modifiable=true thì bytes mới luôn hợp lệ”

Sai. `isModifiableClass` không đánh giá classfile output. Lỗi verifier, method signature, class version, superclass, stack frames vẫn có thể làm thao tác thất bại.

### Lỗi 9 — “Rollback bằng cách tắt boolean là đủ”

Sai với nhiều transformers hoặc sau một lượt redefine. Muốn rollback đáng tin phải lưu **baseline/snapshot có provenance**, biết đã đi qua transformer nào và kiểm tra điều kiện runtime trước khi đưa bytes cũ vào.

### Lỗi 10 — “Cập nhật code là đủ, không cần thử state cũ”

Sai. Redefinition/retransformation không reset static fields hoặc tạo lại instances. Method body mới chạy trên state hiện có; tương thích logic phải được kiểm thử.

### Lỗi 11 — “Method đã thay thì active frame đổi tức thì”

Không. Frame đang chạy có thể vẫn dùng bytecode cũ; các lời gọi mới dùng định nghĩa mới. Phải phân biệt hành vi của frame cũ và invocation mới.

### Lỗi 12 — “Tìm được classfile bytes trong resource là đã có replacement đúng”

Không. Resource cùng tên có thể thuộc phiên bản khác, class loader khác, shaded/nested JAR hoặc quá trình build khác. Kiểm tra provenance, binary name, schema, verifier và tương thích target.

## 12. Checklist vận hành và kiểm thử

### Trước khi chọn API

- [ ] Class đích **đã nạp** hay chưa? Nếu chưa, cân nhắc transform ở initial load.
- [ ] Nguồn bytes chủ đạo là tệp `.class` mới **được build đầy đủ** hay là thuật toán transformer trên input JVM cung cấp?
- [ ] Nếu đã có full replacement bytes, chúng có từ đúng build, đã kiểm tra integrity và class schema chưa?
- [ ] Nếu dùng transformer, code có idempotent và xử lý được bytes sau một lần redefine không?
- [ ] Đã xác định đúng `Class<?>` theo binary name + defining loader/module chưa?
- [ ] JVM có đúng capability cần thiết và target có modifiable không?
- [ ] Có dự định đổi field/method/inheritance ngoài giới hạn hay chỉ method body?
- [ ] Khi cần rollback, đang lưu bản source bytes nào: BASE lúc đầu hay EDIT của lần redefine?

### Khi thực hiện

- [ ] Nếu redefine: đọc classfile bytes hoàn chỉnh, kiểm tra nguồn, tạo `ClassDefinition(target, bytes)`, yêu cầu một nhóm tương thích.
- [ ] Nếu retransform: đăng ký `ClassFileTransformer` phù hợp với `canRetransform=true`, chọn target class set, rồi gọi tường minh `retransformClasses`.
- [ ] Log phân biệt `registered`, `redefine requested`, `retransform requested`, `transform invoked` và `verified`.
- [ ] Có xử lý exception và chính sách fail-fast/degrade rõ ràng, không nuốt lỗi rồi thông báo thành công.
- [ ] Không sửa in-place `classfileBuffer`; nếu transformer tạo bytes thì trả mảng mới hợp lệ.
- [ ] Kiểm tra tác động của các transformers khác trong pipeline.

### Sau khi thực hiện

- [ ] Test invocation mới và trường hợp method đang chạy trong active frame.
- [ ] Test trên static state và instances tồn tại từ trước.
- [ ] So sánh class behavior với mục tiêu, không chỉ dựa vào việc API không ném exception.
- [ ] Test với nhiều class loaders, module boundaries và runtime Java version đích.
- [ ] Xác nhận rollback plan dùng đúng source-of-truth version và không đụng class ngoài phạm vi.
- [ ] Nếu có nhiều class phụ thuộc, kiểm tra tính nhất quán khi thay cùng một lượt.

### Ma trận test gợi ý

| Case | Điều kiện | Kết quả kỳ vọng |
|---|---|---|
| 1 | BASE, patch bật, retransform | LIVE |
| 2 | BASE, patch tắt, retransform | BASE |
| 3 | Redefine sang file EDIT, patch tắt | EDIT |
| 4 | Sau redefine, patch bật, retransform | PIPE |
| 5 | Sau redefine, patch tắt, retransform | EDIT, **không phải BASE** |
| 6 | JVM thiếu `Can-Redefine-Classes`/capability | Không gọi redefine; báo lỗi rõ |
| 7 | JVM thiếu `Can-Retransform-Classes`/capability | Không gọi retransform; báo lỗi rõ |
| 8 | Target `isModifiableClass==false` | Skip/fail có chủ đích |
| 9 | Replacement classfile sai binary name | Lượt redefine thất bại |
| 10 | Replacement làm thay đổi field schema bị cấm | JVM từ chối theo giới hạn |
| 11 | Nhiều transformer, trong đó có `canRetransform=false` | Khi retransform, kết quả trước của incapable vẫn được tái áp dụng |
| 12 | Nhóm 2 class, một class bytes không hợp lệ | Cả lượt không cài đặt class nào |

## 13. Câu hỏi tự kiểm tra

**1.** Có tệp `InvoiceService.class` mới sau khi sửa body method, muốn áp dụng nguyên phiên bản biên dịch cho class đã load. Chọn gì?

> Thường cân nhắc `redefineClasses(new ClassDefinition(target, bytes))` vì caller có full classfile mới và muốn dùng nó làm định nghĩa cơ sở.

**2.** Một profiler đã có transformer và muốn thêm instrumentation vào các method thuộc class đang chạy, chưa có tệp class mới. Chọn gì?

> `retransformClasses(target)` với transformer đăng ký `canRetransform=true`, sau khi kiểm tra capability và modifiability.

**3.** Có đúng là `redefineClasses` không gọi `ClassFileTransformer` không?

> Không. Redefinition cũng đi qua pipeline transformer; replacement bytes có thể bị biến đổi trước khi JVM kiểm tra và cài đặt.

**4.** Vì sao retransform sau một lần redefine không nhất thiết dùng bytes từ JAR ban đầu?

> Vì nguồn cơ sở cho retransform được quản lý theo **lần class load hoặc lần redefine gần nhất**. Khi redefine bằng bytes EDIT, EDIT trở thành cơ sở mới.

**5.** Tắt transformer capable rồi retransform có luôn trả về code nguyên thủy không?

> Không. Có thể chỉ bỏ tác động của transformer đó, còn các biến đổi không capable hoặc transformer khác vẫn có hiệu lực. Sau redefine, cơ sở cũng đã thay đổi.

**6.** Một class modifiable và `isRedefineClassesSupported()==true` có thể thêm field mới một cách tùy ý không?

> Không. Những thay đổi schema phải tuân theo giới hạn JVM TI; nhiều JVM chỉ hỗ trợ thay đổi method body và những thuộc tính nhất định.

**7.** Mọi instances đang tồn tại có được tạo lại sau redefine không?

> Không. Instances và static state không được tự động tái tạo/reset. Active frames có thể tiếp tục bytecode cũ.

**8.** Nếu chỉ mới đăng ký transformer với `addTransformer(t,true)`, class đã load có được biến đổi lại chưa?

> Chưa. Muốn xử lý lớp cũ cần yêu cầu `retransformClasses(target)`; đăng ký không tự replay toàn bộ loaded classes.

**9.** Khi redefine một class trong plugin loader, chỉ biết tên `com.example.Service` đã đủ chưa?

> Chưa. Cần `Class<?>` đúng defining loader và bytes có binary name tương ứng. Tên chuỗi một mình không xác định class runtime duy nhất.

**10.** Trong demo, vì sao chuỗi cuối là EDIT thay vì BASE?

> `redefineClasses` đã thay nguồn cơ sở bằng classfile EDIT. Lượt retransform khi patch tắt chạy lại từ cơ sở EDIT và trả `null`, nên method tiếp tục trả EDIT.

## 14. Nguồn đặc tả chính thức

- Java SE 17, `Instrumentation`: `redefineClasses`, `retransformClasses`, nguồn bytes, transformer replay, capability, active frames, static fields và lỗi: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: thứ tự transformer, đầu vào theo load/redefine/retransform, `return null` và `canRetransform`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `ClassDefinition`: class target + định nghĩa classfile bytes dùng cho redefine: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Java SE 17, `java.lang.instrument`: manifest `Can-Redefine-Classes` và `Can-Retransform-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JVM TI `RedefineClasses` và `RetransformClasses`: giới hạn class schema/hành vi runtime: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
