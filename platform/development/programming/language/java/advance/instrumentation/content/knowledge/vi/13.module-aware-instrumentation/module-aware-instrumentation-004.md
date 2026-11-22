# Phân biệt reads, exports và opens trong Java Module System và Instrumentation

Khi một Java agent thay đổi bytecode của lớp trong **named module**, lỗi thường không nằm ở bản thân lệnh instrument mà ở **quan hệ truy cập giữa các module**. Một đoạn bytecode mới gọi helper có thể gặp **IllegalAccessError** dù helper là **public**; một thư viện dùng reflection có thể gặp **InaccessibleObjectException** dù đã dùng **setAccessible(true)**. Để hiểu và sửa đúng, phải phân biệt ba quan hệ của Java Platform Module System (JPMS):

- **reads**: module A có quan hệ **đọc** module B không?
- **exports**: module B có **xuất package p** để mã ở A truy cập các kiểu và thành viên có mức truy cập thích hợp không?
- **opens**: module B có **mở package p** cho A thực hiện **deep reflection** lên cả thành viên không public không?

Đây là **ba việc khác nhau**, có chiều và đối tượng riêng. Với Instrumentation, agent thường dùng **Instrumentation.redefineModule(...)** để bổ sung các quan hệ ấy **tại runtime**. API này có thể **mở rộng**, không thể dùng để thu hồi một read edge hoặc quyền export/open đã cấp. Nó cũng không tự cập nhật **module-info.java** hay khiến mã vốn không biên dịch được đột nhiên biên dịch được nếu bạn chỉ thêm quyền sau khi JVM khởi động.

Bài học sử dụng Java 17+, có bảng quyết định quyền truy cập, các mẫu cấu hình module-info.java và các tùy chọn JVM, cùng **một ví dụ hai named modules + Java agent có thể biên dịch và chạy**. Ví dụ thể hiện cả trường hợp **chỉ mở package mà không khai báo exports**: ở runtime, **Module.isExported(package, targetModule)** vẫn có thể trả về **true** vì một package đã mở được xem là exported tới module ấy *tại runtime*; điều đó **không tương đương exports tại compile time**.

## 1. Mô hình ba quan hệ

Hãy đặt tên:

- **C**: module tiêu thụ code, ví dụ **demo.client**.
- **T**: module định nghĩa kiểu cần truy cập, ví dụ **demo.target**.
- **p**: package thuộc T, ví dụ **demo.hidden**.

~~~text
Module C = demo.client
    │
    ├── reads ───────────────────────────► Module T = demo.target
    │                                          │
    │                                          ├── package p = demo.hidden
    │                                          │
    │◄── T exports p to C ────────────────────┤ cho truy cập public API
    │                                          │
    │◄── T opens p to C ──────────────────────┘ cho deep reflection
    │
    └── C có thể đồng thời cần cả read edge lẫn export/open.
~~~

**Chiều rất quan trọng.** A cần gọi public method ở B nghĩa là **A reads B**, nhưng quyền expose package phải được thiết lập ở **B exports package to A**. Nếu muốn đọc private field bằng reflection thì **B opens package to A**. Không thể sửa mọi thứ bằng cách addReads ở B hoặc addOpens trên một module không sở hữu package p.

### 1.1. Ba câu hỏi kiểm tra nhanh

Giả sử method trong **demo.client** cần gọi **public static** method trong **demo.hidden.Vault** do **demo.target** định nghĩa:

1. **demo.client đọc demo.target chưa?** Nếu chưa, class ngoài module không phải quan hệ phụ thuộc hợp lệ cho liên kết kiểu thông thường.
2. **demo.target có xuất demo.hidden tới demo.client chưa?** Nếu chưa, public class ở đó vẫn bị bao đóng ở biên module; chỉ sửa reads là chưa đủ.
3. **Có cần vượt kiểm tra truy cập Java để lấy private member bằng reflection không?** Nếu có, cần **opens** chứ không chỉ exports.

Nói ngắn: **reads quyết định phụ thuộc module; exports quyết định public API; opens quyết định deep reflection**. Cần cả quyền truy cập ở cấp Java member/class, class loader nhìn thấy định nghĩa và module/package policy; JPMS không làm biến mất các quy tắc **public/private/protected/package-private**.

## 2. So sánh reads, exports và opens

| Khái niệm | Ai cấp? | Cú pháp module-info.java | Quyền mang lại | Điều KHÔNG tự mang lại |
| --- | --- | --- | --- | --- |
| **reads** | Module gọi C | **requires demo.target;** | C đọc T; cho phép quan hệ phụ thuộc hợp lệ | Không tự xuất package không public ra C |
| **exports** | Module sở hữu package T | **exports demo.api;** hoặc **exports demo.api to demo.client;** | Public types và public/protected members phù hợp có thể truy cập ở compile time và runtime khi module consumer đọc T | Không mở private members cho deep reflection |
| **opens** | Module sở hữu package T | **opens demo.hidden;** hoặc **opens demo.hidden to demo.client;** | Deep reflection tại runtime, gồm non-public types/members khi API reflection cho phép; cũng có public access tại runtime | Không xuất package cho mã nguồn consumer ở compile time |
| **open module** | Module T | **open module demo.target { ... }** | Mở mọi package của T cho deep reflection tại runtime | Không tự exports tất cả package cho compiler; không cho phép thêm directive opens riêng |
| **--add-reads** | Launcher/JVM | **--add-reads demo.client=demo.target** | Thêm read edge theo phạm vi launcher | Không sửa export/open |
| **--add-exports** | Launcher/JVM | **--add-exports demo.target/demo.hidden=demo.client** | Nới public access tới package, dùng được ở compile/runtime khi đặt đúng giai đoạn | Không cấp private reflection |
| **--add-opens** | Launcher/JVM | **--add-opens demo.target/demo.hidden=demo.client** | Mở package cho reflection tại runtime | Không thay module-info.java và không tương đương compile-time exports |
| **redefineModule** | Agent có Instrumentation | **extraReads / extraExports / extraOpens** | Thêm quan hệ ở runtime | Không xóa/revoke quan hệ cũ, không rewrite descriptor ở nguồn |

**Lưu ý qualified/unqualified:** **exports p** hoặc **opens p** không ghi **to** thì tác dụng tới tất cả module phù hợp; **exports p to A** hoặc **opens p to A** giới hạn cho module A (và những module được chỉ định). Khi làm agent, **chỉ mở cho module cần thiết** thay vì blanket access tới mọi module.

## 3. Reads: khả năng nhìn thấy phụ thuộc module

Một named module khai báo phụ thuộc module khác bằng **requires**:

~~~java
// File module-info.java của module demo.client.
// Chỉ là ví dụ cú pháp JPMS, không phải class thông thường.
module demo.client {
    requires demo.target;
}
~~~

Trong module descriptor, **requires demo.target** tạo quan hệ đọc từ **demo.client → demo.target**. Ở runtime, ta có thể hỏi:

~~~java
// Đoạn minh họa, giả sử hai Module object đã có.
boolean readable = clientModule.canRead(targetModule);
~~~

**canRead** nói về **quan hệ giữa hai module**; nó không kiểm tra package cụ thể hoặc quyền truy cập thành viên. Với named module, mặc định nó đọc chính nó và **java.base**; những module khác phải được thiết lập qua module descriptor, quy tắc module graph hoặc thay đổi runtime thích hợp. **requires transitive** có thể làm một module khác đọc thêm module phụ thuộc theo cơ chế transitive readability; không nên suy luận read edges chỉ từ requires trực tiếp khi debug.

Một read edge hợp lệ **chưa đủ** để truy cập một public class trong package không được export:

~~~text
client.canRead(target)       == true
target.isExported(p, client) == false
→ Không có ordinary public access tới public class trong p.
~~~

### 3.1. Thêm read edge khi có agent

Trong ngữ cảnh agent, cần gọi **redefineModule** trên **consumer**, vì consumer là bên phải đọc target:

~~~java
// Đoạn minh họa, có inst, client, target hợp lệ.
inst.redefineModule(
    client,
    Set.of(target), // extraReads
    Map.of(),        // extraExports
    Map.of(),        // extraOpens
    Set.of(),        // extraUses
    Map.of()         // extraProvides
);
~~~

Cả sáu tham số đều có ý nghĩa; bộ **extraReads** chỉ thêm đọc module, không thay đổi export/open trên package của target.

### 3.2. Unnamed module có gì đặc biệt?

Code ở classpath thuộc **unnamed module** của defining class loader. Theo **Module.canRead**, unnamed module **đọc tất cả các module**. Vì vậy dùng một chương trình hoàn toàn trên classpath để chứng minh sự khác biệt khi thêm **reads** thường gây kết luận sai: điều kiện reads vốn đã đúng.

Đó là lý do ví dụ thực hành dùng **hai named modules**. Khi cần agent helper thuộc unnamed module được tham chiếu từ bytecode trong named module, chiều cần xét là **named target module đọc unnamed helper module**, không phải chiều ngược lại. Agent ở classpath đọc named modules theo mặc định, nhưng code được chèn **vào lớp named module** chịu luật truy cập theo module của **lớp đích**.

### 3.3. Class.forName không chứng minh khả năng truy cập API

Trong demo, code ở **demo.client** vẫn có thể tìm được đối tượng **Class<?>** của **demo.hidden.Vault** bằng **Class.forName** vì các module đã được giải quyết và class loader tìm thấy định nghĩa. Việc tìm class bằng tên **không có nghĩa** module client đã có quyền liên kết và gọi public method bằng JVM instruction hay MethodHandles.

Đừng dùng mỗi **Class.forName thành công** để kết luận rằng **reads + exports** đã đủ. Phải kiểm tra **canRead**, **isExported** và thử một thao tác truy cập thực tế.

## 4. Exports: khả năng dùng public API của package

Module sở hữu package có thể xuất nó không điều kiện:

~~~java
// module-info.java của demo.target, ví dụ exports mọi module.
module demo.target {
    exports demo.api;
}
~~~

Hoặc xuất có điều kiện cho một named module:

~~~java
// module-info.java của demo.target, ví dụ qualified exports.
module demo.target {
    exports demo.internal.api to demo.client;
}
~~~

Khi consumer **đọc** module target, Java compiler và JVM cho phép truy cập kiểu thành viên **public** trong package được export, đồng thời vẫn áp dụng kiểm soát Java thông thường. Không thể gọi **private method** của class khác chỉ nhờ exports.

~~~java
// Câu hỏi runtime trên Module object.
boolean toClient = targetModule.isExported(
        "demo.api", clientModule);
boolean toEveryone = targetModule.isExported("demo.api");
~~~

Hai phép kiểm tra có ý nghĩa khác nhau:

- **isExported(p, client)**: package có được xuất **ít nhất tới client** hay không, có tính cả quyền mở package tại runtime.
- **isExported(p)**: xuất không điều kiện cho mọi module **tại runtime**.

**Cả hai phương thức isExported không kiểm tra read edge của client.** Một module có thể export package tới client dù client chưa đọc module đó. Bởi vậy để giải thích truy cập thực tế cần xem **cả đọc và xuất**, không chỉ một boolean.

### 4.1. Public class trong package private-by-module

Một class có thể khai báo **public** nhưng nếu package của nó không được exports tới client thì client vẫn không có quyền truy cập từ ngoài named module theo ordinary Java access:

~~~java
package demo.hidden;

public final class Vault {
    public static String publicInfo() {
        return "PUBLIC_OK";
    }
}
~~~

**public** trong file Java chỉ là một lớp của kiểm soát truy cập; JPMS bổ sung biên module. Đừng đổi public class thành package-private hoặc cố dùng reflection tùy tiện khi lỗi thật là package chưa được exported tới consumer.

### 4.2. Thêm qualified exports bằng Instrumentation

~~~java
// Đoạn minh họa.
inst.redefineModule(
    target,                       // module sở hữu demo.hidden
    Set.of(),                     // không thêm reads ở target
    Map.of("demo.hidden", Set.of(client)),
    Map.of(),
    Set.of(),
    Map.of()
);
~~~

Map có **key là tên package dùng dấu chấm** (**demo.hidden**), không phải internal JVM name kiểu **demo/hidden**. **value** là tập **Module object nhận quyền**, không phải string tên module. Một map entry với tập rỗng là không hợp lệ theo Javadoc.

Nếu target đang không exports package tới client, cấp **reads trên client** và **exports trên target** là hai thay đổi **độc lập có hướng ngược nhau**. Đừng gọi **redefineModule(target, Set.of(client), ...)** rồi tưởng rằng client đọc target.

## 5. Opens: truy cập sâu bằng reflection

**opens** mở package cho **deep reflection**, tức có thể yêu cầu suppression của ordinary Java access checks qua **AccessibleObject.setAccessible(true)** / **trySetAccessible()** hoặc đường **MethodHandles.privateLookupIn** nếu các tiền điều kiện khác thỏa mãn.

~~~java
// module-info.java của demo.target: chỉ client được deep reflect.
module demo.target {
    opens demo.hidden to demo.client;
}
~~~

Code ở **demo.client** có thể:

~~~java
// Đoạn minh họa; có Class<?> vault = ... hợp lệ.
java.lang.reflect.Method secret =
        vault.getDeclaredMethod("secret");

boolean canDeepReflect = secret.trySetAccessible();
if (canDeepReflect) {
    Object value = secret.invoke(null);
}
~~~

Nếu package không open tới module thực thi code reflection, **trySetAccessible()** trả **false**; với **setAccessible(true)** thường nhận **InaccessibleObjectException**. Chỉ exports là **không đủ** cho private method/field thuộc module khác.

**opens không đồng nghĩa export tại compile time.** Câu lệnh **opens p** được JPMS dùng cho runtime; nếu source của client muốn trực tiếp **import demo.hidden.Vault** và biên dịch thông thường, compiler vẫn cần package được **exports** (và client cần reads). Hãy dùng **exports** cho API có chủ đích công khai; dùng **opens** cho reflection framework cần private access.

### 5.1. Sắc thái quan trọng: opens được xem là exported tại runtime

Theo Java SE 17 **Module.isExported(p, other)**, một package đã **open** tới module other được xem là **exported tại runtime** tới other. Do đó:

~~~text
target.isOpen("demo.hidden", client)      == true
target.isExported("demo.hidden", client)  == true
~~~

có thể đồng thời đúng, **ngay cả khi module-info.java không có exports demo.hidden** và agent chỉ thêm quyền **opens**. Việc **isExported=true** ở đây **không có nghĩa compiler đã được cấp compile-time exports**.

Đây là một bẫy khi debug:

- **Module.isExported** quan sát **khả năng truy cập ở runtime**, có tính đến package đã mở.
- **module-info.java** và các option biên dịch quyết định **compile-time visibility**.
- **Module.getDescriptor()** phản ánh module declaration gốc, không biến thành file module-info được viết lại khi agent bổ sung read/export/open động.

Nếu cần biết *đã được khai báo exports bằng directive hay chỉ nhờ opens*, xem thêm **ModuleDescriptor.exports()/opens()**, runtime **isOpen(...)** và cấu hình launcher/agent. Đừng chỉ dựa trên một giá trị **isExported(...)** để suy luận nguồn cấp quyền.

### 5.2. Exports và opens đều có thể qualified

~~~java
// Chỉ là ví dụ module descriptor ở package thuộc demo.target.
module demo.target {
    exports demo.api to demo.client;
    opens demo.internal to demo.framework;
}
~~~

**demo.client** được truy cập public API trong **demo.api**; **demo.framework** được phép deep reflect **demo.internal**. Nếu **demo.client** muốn lấy private field trong **demo.internal**, export khác package không giúp ích. Nếu framework ở **unnamed module**, không thể ghi **to ALL-UNNAMED** như một tên module trong module-info.java; token đặc biệt **ALL-UNNAMED** thuộc cú pháp tùy chọn launcher như **--add-opens**/**--add-exports**.

### 5.3. Open module khác opens từng package

~~~java
// Mọi package trong module có quyền mở ở runtime.
open module demo.target {
    // Các requires/provides/exports nếu cần vẫn có thể xuất hiện.
}
~~~

**open module** mở **mọi package** cho deep reflection; trong một **open module declaration** không được ghi directive **opens** riêng theo JLS. Đây là quyền rộng hơn **opens p to framework** và thường không phù hợp cho module có yêu cầu encapsulation chặt.

## 6. Bảng quyết định quyền truy cập theo thao tác

Giả sử **C** là named module consumer, **T** là named module target sở hữu **p**, lớp trong p là **public**, method public/private như tên gọi.

| C reads T | T exports p to C | T opens p to C | Ordinary public access | Private reflection |
| --- | --- | --- | --- | --- |
| Không | Không | Không | Không | Không |
| Có | Không | Không | Không | Không |
| Có | Có | Không | Có | Không |
| Có | Không | Có | Có **ở runtime** vì open được tính là export runtime | Có |
| Có | Có | Có | Có | Có |
| Không | Có | Không | Thiếu read edge cho ordinary access; reflection có quy tắc riêng | Không |

**Quan trọng:** Reflection qua **java.lang.reflect** mặc định **giả định readability** khi kiểm tra truy cập của reflective object; vì vậy bạn có thể quan sát reflection thành công trong một vài trường hợp mà **client.canRead(target)** không đúng. Đừng lấy điều này làm cớ bỏ qua reads đối với **bytecode instruction/MethodHandles** mà agent chèn vào named module. Từng cơ chế có access checks riêng và nên được thử bằng đúng thao tác mà chương trình thực hiện.

### 6.1. Ba dòng kiểm tra đầu tiên khi debug

~~~java
// Đoạn minh họa.
System.out.println(client.canRead(target));
System.out.println(target.isExported("demo.hidden", client));
System.out.println(target.isOpen("demo.hidden", client));
~~~

Diễn giải:

- **false, false, false**: thiếu mọi quyền cần thiết.
- **true, false, false**: có reads, thiếu public access và deep reflection.
- **true, true, false**: public access ở runtime, không thể suy ra private reflection.
- **true, true, true**: package được open tới client; private reflection có thể được bật theo hợp đồng API.

Phải nhớ **isExported** trả true khi package đã open; dấu **true, true, true** không chứng minh có directive exports riêng.

## 7. Instrumentation.redefineModule: API nối ba quan hệ

Java 17 cung cấp:

~~~java
// Chữ ký API; đoạn tham khảo, không phải file Java độc lập.
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
~~~

Giải thích các đối số:

| Đối số | Tác dụng |
| --- | --- |
| **module** | Module đang được bổ sung quyền/metadata |
| **extraReads** | Những module khác mà module này được phép đọc thêm |
| **extraExports** | Những package **của module này** được export thêm tới các module khác |
| **extraOpens** | Những package **của module này** được open thêm tới các module khác |
| **extraUses** | Các service type mà module được phép dùng thêm qua ServiceLoader |
| **extraProvides** | Các implementation service mới mà module cung cấp |

Hai đối số cuối là **service bindings**, không phải reads/exports/opens, nhưng phải truyền **Set/Map hợp lệ**, thường là **Set.of()** và **Map.of()**, khi chỉ cần thay ba quan hệ truy cập.

### 7.1. Cấp reads rồi exports rồi opens

~~~java
// Đoạn minh họa trong một agent đã có inst, client, target.
inst.redefineModule(
    client, Set.of(target),
    Map.of(), Map.of(), Set.of(), Map.of()
);

inst.redefineModule(
    target, Set.of(),
    Map.of("demo.hidden", Set.of(client)),
    Map.of(), Set.of(), Map.of()
);

inst.redefineModule(
    target, Set.of(),
    Map.of(),
    Map.of("demo.hidden", Set.of(client)),
    Set.of(), Map.of()
);
~~~

Thực tế có thể gộp **extraExports** và **extraOpens** vào **một lời gọi redefineModule(target,...)** vì cùng sở hữu package. Read edge phải thêm vào **client**, nên thông thường vẫn là một lời gọi khác. Các quyền này đều **chỉ mở rộng**; không có API redefineModule để “đóng lại package” về trạng thái cũ.

### 7.2. Tính an toàn và phạm vi

- Gọi **inst.isModifiableModule(target)** trước khi sửa; khi không modifiable, **redefineModule** có thể ném **UnmodifiableModuleException**.
- Phương thức được Javadoc mô tả **an toàn cho sử dụng đồng thời** để nhiều agent bổ sung quan hệ cùng module; điều này **không có nghĩa** các agent tự đồng thuận về quyền cần cấp hoặc có thể rollback những quyền đã mở.
- **redefineModule** trên **unnamed module** là **no-op**, và **isModifiableModule** trên unnamed module trả **true**; điều này dễ khiến log “đã gọi API” nhưng chẳng có gì thực sự thay đổi.
- Package key của **extraExports/extraOpens** phải thuộc module đang được thay; sai package hoặc tập đích rỗng gây **IllegalArgumentException**.
- Arguments null hoặc phần tử null trong các Set/Map gây **NullPointerException**.
- **redefineModule** không cho thu hẹp existing reads/exports/opens, services uses/provides; nếu cần hồi lại biên module đã nới, thường phải tính tới **khởi động JVM mới**.
- Không coi redefineModule là cách bypass mọi lỗi class loader: helper phải **thực sự được loader phù hợp tìm thấy**, tên method/descriptor phải đúng và bytecode phải hợp lệ.

### 7.3. Module.addReads / addExports / addOpens không phải một bản thay thế vô điều kiện

Java cũng có **Module.addReads**, **Module.addExports**, **Module.addOpens**. Tuy nhiên, các method này có **điều kiện caller/module authority**: ví dụ **Module.addReads** và **addExports** trên named module yêu cầu caller thuộc chính module đó; **addOpens** có điều kiện package đã được mở cho caller thích hợp. Agent trong unnamed module **không nên giả định** có thể gọi trực tiếp trên bất kỳ named module nào.

**Instrumentation.redefineModule** tồn tại để phục vụ agent cần bổ sung quan hệ truy cập giữa các module trong instrumentation. Không dùng reflection phá kiểm tra module để gọi các method add* theo cách không được API hỗ trợ.

## 8. Bài thực hành Java 17+: quan sát 5 trạng thái quyền truy cập

Đây là ví dụ **có thể build/run** trên JDK 17 trở lên mà không dùng thư viện ngoài. Ta tạo hai named modules:

- **demo.target**: chứa **demo.hidden.Vault**, package không exports và không opens trong module-info.java.
- **demo.client**: chứa **demo.client.Probe**, module không requires demo.target.
- **AccessAgent**: startup Java agent (unnamed module trong classpath) nhận **Instrumentation** từ JVM, tùy mode mà bổ sung read/export/open cho đúng hai module ở **boot layer**.

**Probe** đọc trạng thái graph, thử gọi **publicInfo()** bằng **MethodHandles.lookup().findStatic(...)** và thử **trySetAccessible** với private method **secret()**. MethodHandles lookup buộc phải kiểm tra điều kiện quyền truy cập theo lookup class; ví dụ này phù hợp để so sánh với ordinary bytecode access. Một method reflection bình thường có variation về readability, do đó không thay thế kiểm thử đó.

### 8.1. Cấu trúc file

~~~text
jpms-access-demo/
  src/
    demo.target/
      module-info.java
      demo/
        hidden/
          Vault.java
    demo.client/
      module-info.java
      demo/
        client/
          Probe.java
  agent/
    AccessAgent.java
    agent.mf
~~~

**Không** đặt **Vault.java** và **Probe.java** vào cùng một unnamed module, vì như vậy sẽ mất trường hợp thiếu read edge.

### 8.2. Module sở hữu package: demo.target

**File src/demo.target/module-info.java**

~~~java
module demo.target {
    // Không export hoặc open demo.hidden ở compile time.
}
~~~

**File src/demo.target/demo/hidden/Vault.java**

~~~java
package demo.hidden;

public final class Vault {
    public static String publicInfo() {
        return "PUBLIC_OK";
    }

    private static String secret() {
        return "SECRET_OK";
    }
}
~~~

Chú ý: class **public**, method **publicInfo()** cũng public, nhưng package **demo.hidden** không xuất ra module client. Private method **secret()** chỉ phục vụ phép thử deep reflection.

### 8.3. Named module consumer: demo.client

**File src/demo.client/module-info.java**

~~~java
module demo.client {
    // Cố ý không requires demo.target.
}
~~~

**File src/demo.client/demo/client/Probe.java**

~~~java
package demo.client;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class Probe {
    public static void main(String[] args) throws Throwable {
        Module client = Probe.class.getModule();
        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();

        // Class.forName thành công trong cấu hình demo,
        // nhưng không có nghĩa được liên kết public/private.
        Class<?> vault = Class.forName("demo.hidden.Vault");

        System.out.println("READS=" + client.canRead(target));
        System.out.println("EXPORTED=" +
                target.isExported("demo.hidden", client));
        System.out.println("OPEN=" +
                target.isOpen("demo.hidden", client));

        // Tạo MethodHandle với quyền của Probe trong named module.
        try {
            MethodHandle mh = MethodHandles.lookup().findStatic(
                    vault,
                    "publicInfo",
                    MethodType.methodType(String.class));
            System.out.println("PUBLIC=" +
                    (String) mh.invokeExact());
        } catch (IllegalAccessException error) {
            System.out.println("PUBLIC=DENIED");
        }

        Method secret = vault.getDeclaredMethod("secret");
        boolean deep = secret.trySetAccessible();
        System.out.println("DEEP=" + deep);
        if (deep) {
            System.out.println("PRIVATE=" + secret.invoke(null));
        }
    }
}
~~~

**Vì sao dùng MethodHandles ở đây?** Trong demo, **MethodHandles.lookup()** lấy lookup context từ named module **demo.client**. Khi tạo handle tới public method của class ở module khác, quyền của lookup class phản ánh read edge + public access. Ngược lại, Core Reflection có quy tắc “assume readability” trong access checks của reflected objects, nên dùng riêng **Method.invoke** để chứng minh reads có thể tạo ra câu trả lời gây hiểu nhầm.

**Không** cần import **demo.hidden.Vault** trong source consumer (và trong trạng thái ban đầu import ấy không biên dịch hợp lệ). Ta dùng tên string để tải Class object từ module đã được launcher resolve, rồi thử những thao tác mà JPMS kiểm soát.

### 8.4. Java agent bổ sung module edges

**File agent/AccessAgent.java**

~~~java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(
            String mode, Instrumentation inst) {

        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();
        Module client = ModuleLayer.boot()
                .findModule("demo.client").orElseThrow();

        if (!inst.isModifiableModule(target)
                || !inst.isModifiableModule(client)) {
            throw new IllegalStateException(
                    "Modules not modifiable");
        }

        if (!Set.of(
                "none", "reads", "exports", "opens", "openOnly")
                .contains(mode)) {
            throw new IllegalArgumentException(
                    "Unknown mode: " + mode);
        }

        // Chỉ mở rộng đồ thị read edge từ client sang target.
        if (!"none".equals(mode)) {
            inst.redefineModule(
                    client,
                    Set.of(target),
                    Map.of(), Map.of(), Set.of(), Map.of());
        }

        // Xuất public API của package target cho client.
        if ("exports".equals(mode) || "opens".equals(mode)) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of("demo.hidden", Set.of(client)),
                    Map.of(),
                    Set.of(),
                    Map.of());
        }

        // Mở package cho private reflection.
        // openOnly chỉ thêm reads + opens, không thêm exports riêng.
        if ("opens".equals(mode) || "openOnly".equals(mode)) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of(),
                    Map.of("demo.hidden", Set.of(client)),
                    Set.of(),
                    Map.of());
        }
    }
}
~~~

**Năm mode có ý nghĩa:**

| Mode | extraReads client→target | extraExports demo.hidden→client | extraOpens demo.hidden→client |
| --- | --- | --- | --- |
| **none** | Không | Không | Không |
| **reads** | Có | Không | Không |
| **exports** | Có | Có | Không |
| **opens** | Có | Có | Có |
| **openOnly** | Có | Không | Có |

Tên **openOnly** chỉ có nghĩa *không gọi extraExports*, **không có nghĩa** thiếu read edge. Lượt mode này chủ đích chứng minh rằng **isExported(package, client)** vẫn trở thành true ở runtime khi chỉ cấp **opens** cho package.

### 8.5. File manifest

**File agent/agent.mf** (giữ newline ở cuối):

~~~text
Manifest-Version: 1.0
Premain-Class: AccessAgent
~~~

Không cần khai báo **Can-Retransform-Classes** hay **Can-Redefine-Classes** cho demo này. Hai capability ấy liên quan đến class retransform/redefine, **không phải** điều kiện mặc định cho **Instrumentation.redefineModule**. Agent chỉ thực hiện bổ sung edges của named modules khi startup.

### 8.6. Build với javac --release 17 và jar

Từ thư mục gốc dự án, dùng shell POSIX:

~~~bash
mkdir -p out/mods/demo.target out/mods/demo.client out/agent

javac --release 17 -d out/mods/demo.target \
  src/demo.target/module-info.java \
  src/demo.target/demo/hidden/Vault.java

javac --release 17 -d out/mods/demo.client \
  src/demo.client/module-info.java \
  src/demo.client/demo/client/Probe.java

javac --release 17 -d out/agent agent/AccessAgent.java

jar cfm access-agent.jar agent/agent.mf \
  -C out/agent AccessAgent.class
~~~

Dấu **\\** ở cuối dòng là cú pháp nối dòng trong shell POSIX; trên PowerShell hoặc cmd.exe có thể viết **mỗi lệnh javac/jar trên một dòng**. Lưu ý **out/mods** phải chứa các thư mục module **demo.target** và **demo.client**, mỗi thư mục có **module-info.class**. Bạn có thể kiểm tra:

~~~bash
jar tf access-agent.jar
~~~

Phải thấy **META-INF/MANIFEST.MF** và **AccessAgent.class**. Ví dụ sử dụng **startup agent**, không có **agentmain** hay dynamic attach.

### 8.7. Chạy mode none: chưa có quan hệ nào

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=none \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=false
EXPORTED=false
OPEN=false
PUBLIC=DENIED
DEEP=false
~~~

**--add-modules demo.target** bảo đảm module demo.target được giải quyết vào boot layer ngay cả khi demo.client không requires nó, giúp agent và Probe lấy **Module object**. Mode none không thêm edges. MethodHandles không được tạo cho publicInfo do thiếu quyền; private reflection cũng không được bật.

### 8.8. Chạy mode reads: chỉ thêm quan hệ đọc

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=reads \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=false
OPEN=false
PUBLIC=DENIED
DEEP=false
~~~

**READS=true** cho thấy client có read edge tới target. Nhưng package **demo.hidden** vẫn không exports và không opens, nên public method handle vẫn bị từ chối và private deep reflection vẫn thất bại.

Đây là lỗi chẩn đoán thường thấy với agent: đã thêm **extraReads** nhưng method được chèn vẫn không link tới public helper vì module chứa helper chưa export package tương ứng.

### 8.9. Chạy mode exports: public access thành công

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=exports \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=false
PUBLIC=PUBLIC_OK
DEEP=false
~~~

**Public method handle** nay tạo và gọi được. Nhưng private method **secret()** vẫn không có quyền suppress access checks, nên **DEEP=false**. **exports** không giống **opens**.

### 8.10. Chạy mode opens: bổ sung deep reflection

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=opens \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=true
PUBLIC=PUBLIC_OK
DEEP=true
PRIVATE=SECRET_OK
~~~

Ở đây Agent đã thêm cả reads, exports và opens. **trySetAccessible()** của private method thành công, rồi reflection invoke trả **SECRET_OK**.

### 8.11. Chạy mode openOnly: opens tạo runtime export

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=openOnly \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=true
PUBLIC=PUBLIC_OK
DEEP=true
PRIVATE=SECRET_OK
~~~

Nhìn kỹ **AccessAgent**: mode **openOnly** **không gọi extraExports** cho demo.hidden! Vậy tại sao **EXPORTED=true**? Vì **Module.isExported(package, target)** trả true đối với package đã **open** cho target module **ở runtime** theo Javadoc. Điều đó không làm module descriptor ở source chứa một directive exports, không khiến javac có quyền import package ấy ở compile time.

**Chạy từng mode trong JVM mới.** Vì redefineModule không thu hồi quyền, nếu thử none→reads→exports→opens liên tục trong **cùng một process**, quyền của các bước trước vẫn tồn tại. Các lệnh trên cố ý tạo **một process mới mỗi mode**, giúp output đo chính xác trạng thái của mode đó.

### 8.12. Kết quả kiểm chứng thực tế của ví dụ

Bộ source này đã được biên dịch bằng **javac --release 17** và chạy với một JDK tương thích trên JVM thử nghiệm. Các output **none, reads, exports, opens và openOnly** ở trên là kết quả của năm lượt chạy riêng. Tại môi trường dự án khác, nếu JVM không cho sửa module, module không được resolve hoặc JAR manifest sai, ứng dụng có thể thất bại trước bước Probe; khi đó cần kiểm tra nguyên nhân chứ không thay output mong đợi một cách tùy tiện.

## 9. So sánh với tùy chọn JVM --add-reads, --add-exports, --add-opens

Không nhất thiết phải dùng agent để thử module edges. Launcher Java hỗ trợ các tùy chọn:

~~~bash
# Read edge tại runtime.
--add-reads demo.client=demo.target

# Public access cho named module consumer.
--add-exports demo.target/demo.hidden=demo.client

# Deep reflection cho named module consumer.
--add-opens demo.target/demo.hidden=demo.client
~~~

Các dòng trên là **minh họa cú pháp option**, không phải lệnh shell độc lập. Trên command line thực, đưa chúng trước **-m** và bảo đảm các module đã được resolve. Có thể kết hợp:

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  --add-reads demo.client=demo.target \
  --add-exports demo.target/demo.hidden=demo.client \
  --add-opens demo.target/demo.hidden=demo.client \
  -m demo.client/demo.client.Probe
~~~

Khi quyền được cấu hình đúng tại runtime, output tương đương mode **opens**. Khác biệt:

- **--add-reads/exports/opens** cấu hình ở launcher; thuận tiện cho một ứng dụng hoặc test mà không phải viết agent.
- **Instrumentation.redefineModule** thêm edges **trong JVM đang chạy** sau khi agent được nạp và có Module object thích hợp.
- **module-info.java** khai báo hợp đồng dependency/API tĩnh, là lựa chọn ưu tiên khi bạn **sở hữu source** và quyền nên tồn tại ở compile time.
- **--add-exports** có thể dùng cả **javac** lẫn **java** để xử lý compile-time/runtime public access theo nhu cầu; chỉ truyền option ở **java** không khiến **javac đã chạy trước đó** được nhìn thấy package không exports.
- **--add-opens** là quyền mở runtime, không phải cách compile direct import tới package hidden.

### 9.1. ALL-UNNAMED không phải tên module thật

Với thư viện chạy ở classpath, có thể thấy:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

**ALL-UNNAMED** là token đặc biệt của launcher để cấp quyền tới **mọi unnamed module**, không phải một Module object hoặc module name dùng trong **Map<String, Set<Module>>** của redefineModule. Khi agent sử dụng API, phải lấy **Module object** của consumer cụ thể, chẳng hạn **someAgentClass.getModule()** nếu nó nằm trong unnamed module.

Không tự động thêm **--add-opens java.base/...=ALL-UNNAMED** vào mọi ứng dụng nếu chỉ cần một package khác và một named module cụ thể. Đây là mở rộng quyền sâu có hệ quả bảo mật/bảo trì.

### 9.2. Có thể thêm read edge mà không thêm exports?

Có, và như demo **reads** chứng minh, quan hệ đọc được mở nhưng public access tới package hidden **vẫn bị chặn**. Tương tự, chỉ thêm exports mà không thêm reads có thể khiến **target.isExported(p,client) == true** nhưng đường ordinary access vẫn thiếu read edge. Hãy kiểm tra **đúng cặp module** và **đúng package**.

## 10. Áp dụng vào bytecode instrumentation: helper có được gọi không?

Giả sử target class được định nghĩa trong module **com.acme.application**. Một ClassFileTransformer chèn:

~~~text
INVOKESTATIC com/acme/agent/TraceHooks.enter ()V
~~~

Đây là **đoạn bytecode minh họa**, không phải lệnh Java source. Helper **TraceHooks** thuộc một module khác, ví dụ **com.acme.telemetry**, hoặc thuộc unnamed module của class loader chứa agent runtime.

Để instruction mới có thể link, cần đánh giá:

1. **Class target** thuộc module nào? Dùng **classBeingRedefined.getModule()** khi có hoặc tham số **Module module** của overload **ClassFileTransformer.transform(Module,...)**. Với class load mới, classBeingRedefined thường null nên **Module module** hữu ích hơn.
2. **TraceHooks** thuộc module nào? **TraceHooks.class.getModule()**; có thể là unnamed module.
3. **Target module có đọc helper module không?** Chỉ agent module đọc target module là **không đủ**, vì JVM resolve instruction từ **module của class chứa instruction mới**.
4. **Helper module có export package chứa TraceHooks cho target module không?** Với helper trong unnamed module, mọi package được xem là exported/open tại runtime, nhưng vẫn phải giải quyết helper qua class loader phù hợp.
5. **TraceHooks/enter có public access hợp lệ và đúng method descriptor?** Reads/exports không tự sửa tên, descriptor hay class loading.
6. **Có dùng reflection lấy private field/method của target không?** Nếu có, cần mở **package target** cho **module đang thực thi code reflection**, có thể khác module helper/agent.

### 10.1. Mẫu cấp reads cho target module

~~~java
// Pseudocode trong agent, các Module object đã xác định.
Module targetModule = targetClass.getModule();
Module helperModule = TraceHooks.class.getModule();

inst.redefineModule(
    targetModule,
    Set.of(helperModule),
    Map.of(), Map.of(), Set.of(), Map.of()
);
~~~

Nếu **helperModule** là unnamed module, agent vẫn có thể yêu cầu named target đọc nó qua extraReads. Nhưng **chỉ thêm read edge chưa bảo đảm class loader của target có thể tìm TraceHooks**. Trong app server nhiều class loader, cần chiến lược đưa helper tới bootstrap/system hoặc classloader visible thích hợp; tránh nạp nhầm phiên bản helper. **Không** tự kết luận chỉ bằng **targetModule.canRead(helperModule)**.

### 10.2. Mẫu mở package target cho agent phản chiếu private state

~~~java
// Pseudocode trong agent; package target thuộc module targetModule.
Module reflector = TraceHooks.class.getModule();

inst.redefineModule(
    targetModule,
    Set.of(),
    Map.of(),
    Map.of("com.acme.internal", Set.of(reflector)),
    Set.of(),
    Map.of()
);
~~~

Đây là **opens trên target module**, vì target sở hữu package có private field. Nếu code thực hiện **setAccessible** lại nằm trong **một module khác với TraceHooks**, phải mở package cho **đúng module thực thi thao tác reflection**. Không phải lúc nào mở cho module của agent entry class cũng đủ.

### 10.3. Có cần exports hay opens cho transformer chỉ đọc classfileBuffer?

Nếu transformer **chỉ nhận byte[] class file và phân tích chúng**, nó thường không cần mở private fields bằng reflection. **ClassFileTransformer.transform** nhận dữ liệu bytecode trực tiếp, không gọi **setAccessible** vào target class để biến đổi từng instruction. Module edges có thể cần khi **bytecode mới gọi helper**, khi framework dùng reflection, hoặc khi agent dùng Java APIs để truy cập types. Tránh nới cả reads, exports, opens “cho chắc” nếu không có nhu cầu thật.

### 10.4. Thứ tự mở quyền và cài bytecode

Một chiến lược an toàn:

1. Xác định đúng **target module**, helper module, classloader và package.
2. Preflight khả năng **isModifiableModule**, package ownership và runtime helper visibility.
3. Cấp **read/export/open edges tối thiểu** bằng redefineModule trước khi gọi retransform/redefine có thể làm bytecode mới link helper.
4. Chạy instrumentation đúng class/method, tạo bytes hợp lệ, giữ classfileBuffer không bị mutate.
5. Quan sát JVM đã chấp nhận class và **method mới chạy được**. Đừng chỉ báo thành công vì redefineModule hoặc ClassFileTransformer không ném exception.

Các quyền module là **runtime permissions được mở rộng một chiều**; nếu bước instrument tiếp theo thất bại, module edges đã thêm có thể **vẫn còn**. Đây không phải transaction chung có rollback giữa redefineModule và retransformClasses/redefineClasses.

## 11. Chẩn đoán lỗi thực tế

| Hiện tượng | Khả năng thường gặp | Cần kiểm tra |
| --- | --- | --- |
| **client.canRead(target) == false** | Thiếu requires / extraReads / --add-reads | Xác định chiều consumer→target |
| **canRead=true nhưng public type inaccessible** | Target chưa exports/open package tới client | isExported(p,client), tên package |
| **IllegalAccessError** khi gọi helper đã chèn | Module access hoặc Java member access sai; cũng có thể descriptor sai | Module of caller/owner, exports, method flags |
| **IllegalAccessException** từ MethodHandles | Lookup class thiếu reads hoặc public access | findStatic access check, canRead và isExported |
| **InaccessibleObjectException** khi setAccessible | Package chưa open cho reflector module | isOpen(p, reflector), đúng module thực thi reflection |
| **trySetAccessible() == false** | Không đủ deep reflection rights | Package opens vs exports, private member rules |
| **ClassNotFoundException / NoClassDefFoundError** | Module resolution/classloader visibility/helper không thấy | Boot layer, defining loader, --add-modules, packaging |
| **isExported=true nhưng javac không import được** | Package chỉ open runtime hoặc chỉ thêm dynamic export | module-info, javac --add-exports, compile-time requires |
| **IllegalCallerException khi Module.addReads** | Agent không thuộc named module đang sửa | Sử dụng Instrumentation.redefineModule hợp lệ |
| **IllegalArgumentException trong redefineModule** | Package không thuộc module, export/open tới tập đích rỗng | Module.getPackages(), Map keys, target sets |
| **UnmodifiableModuleException** | Module không cho redefineModule | isModifiableModule |
| **NullPointerException trong redefineModule** | Một đối số hoặc phần tử tập/map null | Set.of/Map.of và validation |
| **Mở package nhưng method link vẫn lỗi** | Có thể thiếu reads, classloader visibility hoặc method ABI | Đối chiếu bytecode caller, owner và descriptor |

### 11.1. Log đúng ba chiều để tránh nhầm

~~~text
SOURCE_MODULE=com.acme.application
HELPER_MODULE=com.acme.telemetry
SOURCE_READS_HELPER=true
HELPER_PACKAGE=com.acme.trace
HELPER_PACKAGE_EXPORTED_TO_SOURCE=true
TARGET_INTERNAL_PACKAGE=com.acme.internal
TARGET_INTERNAL_PACKAGE_OPEN_TO_REFLECTOR=false
~~~

Đây là **mẫu log chẩn đoán do agent tự xây**, không phải output tự động từ Java 17. Nên luôn ghi **defining class loader identity** và **Module object** tương ứng ở các môi trường có nhiều module layer/plugin.

### 11.2. Một method không cần deep reflection vẫn bị InaccessibleObjectException?

Nếu framework đang gọi **setAccessible(true)** lên một member không public dù mục tiêu logic chỉ là gọi public API, lỗi có thể xuất phát từ **cách framework triển khai reflection**, không phải từ yêu cầu nghiệp vụ. Nếu bạn kiểm soát framework, có thể đổi sang public API để không cần opens. Trước khi mở package JDK internals hay thư viện bên thứ ba, hãy đánh giá liệu quyền ấy thực sự cần hay không.

### 11.3. Vì sao lỗi có thể vẫn xảy ra sau khi thêm quyền?

JVM linkage có tính chất caching failure trong một số đường resolution. **Module.addExports** Javadoc lưu ý: sau một lần symbolic reference resolution thất bại do linkage error, những lần resolution tiếp theo của cùng symbolic reference vẫn có thể ném cùng lỗi. Vì vậy đừng thiết kế agent cố ý cho method chạy và ném **IllegalAccessError** rồi mới bổ sung exports như biện pháp chữa hậu quả duy nhất. Tốt hơn là **thiết lập edges trước khi chạy code mới**, và kiểm tra trên JVM mới trong test.

## 12. Tối thiểu hóa phạm vi quyền và hậu quả bảo mật

**opens** có quyền rộng hơn **exports**: nó tạo điều kiện cho code ở module được mở gói **bỏ qua kiểm tra Java access với private/package-private members** thông qua những API reflection cho phép. Cấp **opens** vô điều kiện cho một package chứa dữ liệu nội bộ có thể làm tăng phạm vi truy cập không mong muốn. Vì vậy:

- Chỉ cấp **extraReads** tới helper module cần thiết.
- Chỉ cấp **extraExports** cho package public helper mà code instrumented phải link.
- Chỉ cấp **extraOpens** cho package thực sự cần reflection không public, tới **đúng reflector module**.
- Tránh **ALL-UNNAMED** nếu có thể dùng named module cụ thể; tránh **open module** nếu chỉ một package cần mở.
- Kiểm tra module layer/classloader: một module tên giống nhau ở layer khác có thể là **Module object khác**, không thể suy ra quyền chỉ từ string tên.
- Ghi lại module edges đã mở để audit; **redefineModule không có thao tác thu hẹp**, nên thay đổi quyền thường kéo dài đến hết đời JVM.
- Không trộn quyền JPMS với ý nghĩa security sandbox tuyệt đối: module system là cơ chế **encapsulation/dependency**, không nên coi exports/opens là biên giới bảo mật ngăn mã độc trong cùng tiến trình được phép thực thi.
- Kiểm tra dependency của Java agent trước khi thêm classloader search path, vì một class helper trùng tên có thể dẫn đến **LinkageError** hoặc thay đổi class identity.

## 13. Sai lầm phổ biến và cách sửa

1. **Nhầm “reads module” với “exports package”:** **requires demo.target** không làm package **demo.hidden** trở thành public API. Cần exports/open phía target.
2. **Nhầm “exports public” với “opens private”:** public method chạy được không có nghĩa private field có thể setAccessible. Cần opens.
3. **Cho rằng opens không ảnh hưởng isExported:** ở **runtime**, package mở được xem như exported tới module nhận quyền. Nhưng compiler vẫn không được mặc định import package chỉ opens.
4. **Cấp extraReads sai hướng:** muốn class target gọi helper thì **target module phải đọc helper module**. Đừng thêm helper→target thay thế.
5. **Thêm extraExports trên consumer thay vì owner:** package key bắt buộc thuộc module đang redefine; target sở hữu package cần xuất.
6. **Dùng dấu slash trong package key:** redefineModule cần **com.example.internal**, không phải JVM internal name **com/example/internal**.
7. **Dùng string tên module thay Set<Module>:** API nhận Module object, nên phải resolve đúng boot/custom layer và class loader.
8. **Lấy module agent entry thay module thực thi reflection:** cần mở package tới module của code thực hiện setAccessible, có thể là helper/framework.
9. **Mở quyền ở runtime rồi chờ javac đã biên dịch trước sửa được lỗi:** compilation và runtime khác giai đoạn; tùy chọn javac/module-info phải đúng.
10. **Coi --add-opens là --add-exports compile time:** không đúng. --add-opens phục vụ runtime reflection.
11. **Coi Module.addReads là API đặc quyền cho mọi agent:** named module có caller constraints; dùng Instrumentation.redefineModule khi thích hợp.
12. **Coi isModifiableModule true là chắc chắn open thành công:** package ownership, sets/maps và params vẫn có thể không hợp lệ.
13. **Cho rằng có thể “đóng lại” package sau khi test:** redefineModule không có giảm quyền; chạy JVM mới nếu cần baseline sạch.
14. **Gán mọi IllegalAccessError cho JPMS:** có thể là Java access modifiers, class hierarchy, method descriptor, class loader, verification hoặc cached linkage failure.
15. **Tạo quyền quá rộng thay vì debug:** mở java.base/java.lang cho ALL-UNNAMED khi chỉ cần public helper ở module riêng là vượt mức tối thiểu cần thiết.

## 14. Ma trận test cho Java agent có module boundaries

| Bài test | Cấu hình | Kỳ vọng |
| --- | --- | --- |
| Không mở quyền | named client không requires target, package hidden | reads/exports/open false |
| Chỉ thêm reads | client→target | reads true, public/deep chưa đủ |
| Thêm exports | reads + target exports p→client | public method handle hoạt động, private reflection bị chặn |
| Thêm opens | reads + target opens p→client | deep reflection hoạt động |
| Chỉ opens (không export riêng) | reads + extraOpens | isExported runtime true; không suy ra compile-time exports |
| Deep reflection sai module | p opens tới framework A, code reflection ở B | B không tự được hưởng quyền của A |
| Wrong package key | extraOpens key không thuộc target | IllegalArgumentException |
| Wrong direction | extraReads đặt lên module owner sai | consumer.canRead(target) không đổi |
| Unnamed helper | target named, helper unnamed | target cần read edge khi bytecode mới tham chiếu helper |
| Custom class loader | class cùng tên khác defining loader | cần đúng Class/Module object |
| Named module helper | public TraceHooks package chưa exports | injected bytecode có thể bị IllegalAccessError |
| Add rights sau linkage failure | đã có lỗi trước khi thêm edges | không dựa vào retry cùng reference; test JVM mới |
| Tăng quyền nhiều lần | nhiều agent redefineModule cùng named module | quyền được cộng thêm, không tự thu hồi |
| Bytecode không hợp lệ | đúng edges nhưng wrong stack/frame/descriptor | JVM vẫn có thể từ chối class file |
| Đánh giá runtime thật | test method đã instrument sau khi cài | xác minh helper và reflection chạy thực tế |

## 15. Câu hỏi tự kiểm tra

1. **Module A requires B, A có thể tự động gọi public class trong mọi package của B không?** Không. Package của B phải exports/open phù hợp cho A theo access rules.
2. **Module B exports package p cho A, A có được lấy private field bằng setAccessible(true) không?** Không chỉ nhờ exports; cần p opens cho module đang reflection hoặc điều kiện đặc quyền khác của API.
3. **Một package chỉ opens p to A có khiến isExported(p,A) trả true không?** Có, tại runtime theo Module.isExported; không đồng nghĩa compile-time exports.
4. **A chỉ cần đọc byte[] classfileBuffer trong ClassFileTransformer, có bắt buộc phải opens toàn bộ package target không?** Không. Opens liên quan deep reflection, không phải việc có dữ liệu bytes.
5. **Bytecode mới của lớp trong module A gọi helper ở B: ai reads ai?** A phải đọc B. B phải export package helper cho A hoặc cho quyền runtime phù hợp.
6. **Để agent đọc private member của target bằng reflection, module nào phải opens package?** Module sở hữu member; mở cho module thực thi reflection.
7. **--add-exports có thay được --add-opens cho private field không?** Không; exports chủ yếu public API.
8. **redefineModule có thể xóa extraReads và đóng package đã open không?** Không; phương thức chỉ mở rộng quan hệ.
9. **Tại sao demo dùng hai named modules chứ không dùng classpath consumer?** Vì unnamed module đọc mọi module; khó minh họa thiếu read edge.
10. **Vì sao isExported=true không chứng minh client đọc target?** Module.isExported không kiểm tra read edge; cần canRead riêng.
11. **Class.forName tìm thấy Vault có chứng minh được access không?** Không. Type discovery và quyền dùng member là hai bước khác.
12. **Tại sao mode openOnly vẫn PUBLIC=PUBLIC_OK dù không gọi extraExports?** Package đã opens cho client được xem như exported tại runtime, với read edge cũng được cấp trong mode đó.

## 16. Checklist triển khai Instrumentation.redefineModule

- Tôi đã xác định **module chứa bytecode được chèn** và **module chứa helper/API đích**.
- Tôi xác định **chiều reads đúng**: code consumer đọc module provider.
- Tôi xác định **package provider sở hữu** và quyền **exports** cần cho ordinary public access.
- Tôi chỉ xin **opens** khi có deep reflection vào non-public member.
- **isExported** được diễn giải đúng: opens cũng làm exported tại runtime; method không kiểm tra reads.
- Tôi đã kiểm tra **Module.isNamed**, **Module.canRead**, **isExported(package, other)**, **isOpen(package, other)** và defining loader/module layer.
- **extraExports/extraOpens** dùng tên package **dấu chấm**, map value là **Set<Module> không rỗng** và package tồn tại trong module owner.
- Tôi có handle **Instrumentation** thực từ JVM và dùng **isModifiableModule** khi cần.
- Tôi không giả định **Module.addReads/addExports/addOpens** có thể gọi tùy ý từ agent module khác.
- Quyền cần thiết đã được mở **trước** khi bytecode instrumented được load/resolve/invoke.
- Tôi không trông đợi **redefineModule** thay đổi source **module-info.java**, compile-time visibility hoặc tự rollback.
- Tôi không nhầm Class.forName/transform callback thành bằng chứng helper đã link và method đã chạy.
- Tôi đã kiểm tra cả **normal invocation**, **reflection**, **wrong loader/module**, và lỗi quyền điển hình trên JVM/JDK mục tiêu.
- Tôi chỉ cấp quyền tối thiểu và ghi nhận mọi mở rộng module edges để audit.

## 17. Tài liệu tham khảo chính thức

- [Java SE 17 — java.lang.instrument.Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): **redefineModule**, **isModifiableModule**, các map **extraReads/extraExports/extraOpens**, quy tắc mở rộng và exception.
- [Java SE 17 — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): **canRead**, **isExported**, **isOpen**, named/unnamed module, **addReads/addExports/addOpens** và các giới hạn caller.
- [Java Language Specification SE 17 — §7.7.1 và §7.7.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): cú pháp **requires/exports/opens**, qualified exports/opens và compile-time/runtime accessibility.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): **setAccessible**, **trySetAccessible**, giới hạn deep reflection và quy tắc reflection assume readability.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền lookup class, cross-module access checks và public/private method handles.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): overload transform có **Module** khi instrumentation class loading.
- [OpenJDK Dev.java — --add-exports và --add-opens](https://dev.java/learn/organizing/modules/add-exports-opens/): các tùy chọn launcher khi cần nới encapsulation có kiểm soát.

**Tóm tắt thực hành:** **Consumer phải reads provider; provider phải exports package cho ordinary public access; provider phải opens package cho deep reflection.** Trong Java agent, dùng **Instrumentation.redefineModule** với **đúng Module object, đúng chiều và đúng tên package**, kiểm tra quyền bằng cả **canRead/isExported/isOpen**, rồi thử truy cập thực tế. Nhớ rằng **opens được tính là exports tại runtime nhưng không phải compile-time exports**, và các quyền đã thêm bằng redefineModule **không có thao tác thu hồi trong cùng JVM**.
