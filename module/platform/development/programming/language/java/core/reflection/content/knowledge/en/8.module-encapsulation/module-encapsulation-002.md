# Readability, exports và opens trong Java Platform Module System (JPMS)

Readability, `exports` và `opens` trả lời ba câu hỏi khác nhau về ranh giới module: **module nào được đọc**, **public API nào được sử dụng từ bên ngoài**, và **package nào cho phép deep reflection**. Bài này đi sâu vào cách các quyền phối hợp, kể cả `requires transitive`, `requires static`, qualified exports/opens và quyền runtime khác quyền khai báo.

Dấu hiệu thực tế: ứng dụng gọi public API bình thường, nhưng framework thất bại ở `Field.setAccessible(true)`. Quan hệ đọc và `exports` có thể đã đầy đủ; chính package chứa field chưa `opens` cho module **thực sự thực hiện Reflection**.

## 1. Module, package và module descriptor

Một named module thường có file module-info.java tại gốc source module. Ví dụ:

~~~java
module com.example.billing {
    requires java.sql;
    exports com.example.billing.api;
    opens com.example.billing.entity to com.example.framework;
}
~~~

Ý nghĩa:

- **requires java.sql**: module billing đọc module java.sql và có thể tham chiếu các public type trong package mà java.sql exports.
- **exports com.example.billing.api**: các public type và public member có khả năng truy cập thông thường từ module đọc billing, theo các quy tắc Java visibility.
- **opens com.example.billing.entity to com.example.framework**: module com.example.framework được phép thực hiện *deep reflection* trên package entity, kể cả private field/constructor, khi API hỗ trợ bỏ kiểm tra truy cập.
- Package không exports cũng không opens được **strongly encapsulated** với các module khác, ngoại trừ quyền riêng của code bên trong module.

JPMS không thay thế public/private/protected. Một class package-private không trở thành public chỉ vì package được exports; một private field không thành thành viên public chỉ vì package được opens. JPMS bổ sung **ranh giới truy cập giữa các module** trên các quy tắc visibility Java có sẵn.

## 2. Readability: quan hệ requires giữa module

**Readability** trả lời câu hỏi: “Module A có thể đọc module B hay không?” Trong phần lớn ứng dụng dạng named module, A khai báo requires B để trình biên dịch cho phép tham chiếu trực tiếp các kiểu của B.

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

- Nếu app requires library, app đọc library; nhưng **đọc được chưa đủ** để import một class trong package không exports.
- Mọi named module đều đọc **java.base** một cách ngầm định; không cần khai báo requires java.base.
- Một module đọc chính nó.
- Module.canRead(...) và quan hệ module graph còn có thể bị bổ sung khi sử dụng module layer hoặc tùy chọn JVM; không nên suy diễn mọi quyền từ file module-info.java mà bỏ qua cấu hình thực tế.

### requires transitive và requires static

Giả sử app dùng facade và facade dùng api:

~~~text
com.example.app -> com.example.facade -> com.example.api
~~~

Nếu facade chỉ khai báo:

~~~java
module com.example.facade {
    requires com.example.api;
    exports com.example.facade;
}
~~~

thì app requires facade nhưng **không tự động đọc api** chỉ vì facade đọc api. Khi API public của facade để lộ các type thuộc api và muốn consumer đọc api qua facade, có thể dùng:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

Khi đó một module đọc facade cũng đọc api nhờ quan hệ transitive. Điều này **không tự mở** package của api: api vẫn phải exports package cần dùng.

**requires static** biểu thị dependency bắt buộc ở thời điểm biên dịch, nhưng không buộc dependency đó phải có mặt và được giải quyết khi chạy. Nếu chương trình thực sự dùng type từ module tùy chọn trong một đường chạy, thiếu module đó vẫn có thể gây lỗi. Đây không phải cách mở Reflection.

Có thể kiểm tra readability ở runtime bằng **moduleA.canRead(moduleB)**; trả về boolean, và chỉ kiểm tra cạnh đọc module, không kiểm tra exports/opens của từng package.

## 3. Exports: API thông thường có thể truy cập

Mẫu khai báo:

~~~java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.spi to com.example.plugin;
}
~~~

- **exports p;** cho phép các module có quyền đọc module này truy cập các public type/public member trong package p bằng Java code thông thường.
- **exports p to m;** là *qualified export*: chỉ mở quyền export cho module đích m (hoặc danh sách module được chỉ định); module khác không thể mặc định import API p.
- exports **không cho phép tự ý truy cập private field/private method** của các class trong package.
- exports chỉ tác động đến package đã khai báo; nó không tự động exports subpackage. Ví dụ exports com.example.api **không đồng nghĩa** exports com.example.api.internal.

Cùng một class public, điều kiện truy cập trực tiếp từ một named module khác gồm: module nguồn được đọc, package chứa class được exports phù hợp, bản thân class là public, và thành viên được dùng đáp ứng quy tắc Java visibility.

Nếu package không exported, lệnh import trực tiếp từ module khác thường bị javac báo lỗi kiểu “package ... is not visible”. Thêm requires vào module caller **không giải quyết** lỗi không exports; phải xét lại API boundary hoặc khai báo exports phù hợp.

## 4. Opens: quyền Reflection sâu

Một framework như serializer, dependency injection container hoặc ORM thường cần đọc/gán private field hoặc gọi constructor không public. Khi hai module khác nhau, exports chỉ cho truy cập API public, còn **opens** cho phép Reflection bỏ kiểm tra truy cập đối với mọi type/member trong package đã mở cho module thực hiện Reflection.

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.model to com.example.serializer;
}
~~~

Những điểm cần phân biệt:

- **opens p;** mở package p cho mọi module thực hiện deep reflection.
- **opens p to m;** chỉ mở cho module m; đây là lựa chọn có phạm vi hẹp hơn khi đã biết framework.
- **open module name { ... }** mở tất cả package trong module cho deep reflection tại runtime. Trong open module không dùng thêm lệnh opens từng package. Open module **không tự biến các package thành exports cho việc import khi biên dịch**.
- Package chỉ opens vẫn không phải là API để mã nguồn của module khác import trực tiếp. Compiler kiểm soát điều này dựa trên các exports đã khai báo.
- opens không có nghĩa mọi Reflection call đều thành công: vẫn cần đúng đối tượng, kiểu tham số và xử lý lỗi khi gọi; còn những package chưa mở có thể trả false từ trySetAccessible() hoặc ném InaccessibleObjectException khi setAccessible(true).

Các API liên quan:

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| Class.getDeclaredField/getDeclaredMethod/getDeclaredConstructor | Tra cứu cả thành viên non-public | Lấy metadata chưa đồng nghĩa được phép dùng thành viên |
| AccessibleObject.setAccessible(true) | Đề nghị bỏ kiểm tra access cho thao tác Reflection | Có thể ném InaccessibleObjectException nếu JPMS không cho phép |
| AccessibleObject.trySetAccessible() | Thử mở quyền và nhận boolean | false khi không thể bật quyền theo policy thông thường |
| Module.isOpen(package, targetModule) | Package được mở cho module target? | Đúng khi opens qualified/unqualified phù hợp |
| Module.isExported(package, targetModule) | Package có được xem là exported **ở runtime** cho target? | Package được opens cho target cũng được coi là exported ở runtime |
| Module.canRead(otherModule) | Module hiện tại đọc otherModule? | Không thay thế kiểm tra exports/opens |

**Chi tiết dễ nhầm của API:** Theo JDK 17, nếu package được **opens** cho module m, Module.isExported(package, m) có thể trả **true** vì JVM xem package được mở là exported cho module đó **ở runtime**. Điều này **không có nghĩa** file module-info.java có exports hay javac cho phép import class từ package chỉ opens. Để kiểm tra exports được **khai báo**, đọc **Module.getDescriptor().exports()**.

## 5. Ví dụ chạy được: requires + exports + opens trong Java 17+

Ta tạo hai named modules:

- **com.acme.library** exports package API public, đồng thời opens package internal riêng cho client.
- **com.acme.client** requires library; gọi API public theo cú pháp Java bình thường và dùng Reflection để đọc một private field trong package internal.

### 5.1. Cấu trúc thư mục

Tại thư mục dự án, tạo đúng các file sau:

~~~text
src/
├── com.acme.library/
│   ├── module-info.java
│   └── com/acme/library/
│       ├── api/Service.java
│       └── internal/Secret.java
└── com.acme.client/
    ├── module-info.java
    └── com/acme/client/Main.java
~~~

**File src/com.acme.library/module-info.java:**

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.internal to com.acme.client;
}
~~~

**File src/com.acme.library/com/acme/library/api/Service.java:**

~~~java
package com.acme.library.api;

public final class Service {
    private Service() {}

    public static String greet() {
        return "hello";
    }
}
~~~

**File src/com.acme.library/com/acme/library/internal/Secret.java:**

~~~java
package com.acme.library.internal;

public final class Secret {
    private final String token = "hidden";
}
~~~

Lớp Secret là public để ví dụ rõ ràng rằng **public class trong package không exports vẫn không thể import trực tiếp từ client**. Constructor của Secret không được khai báo tường minh, nên Java tạo default constructor tương ứng với visibility public của class? **Không**: default constructor có cùng access với class public, vì vậy trong trường hợp này là public. Dù vậy, vì package internal chỉ opens cho client, Reflection vẫn cần bật quyền truy cập khi gọi constructor từ module khác.

**File src/com.acme.client/module-info.java:**

~~~java
module com.acme.client {
    requires com.acme.library;
}
~~~

**File src/com.acme.client/com/acme/client/Main.java:**

~~~java
package com.acme.client;

import com.acme.library.api.Service;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module client = Main.class.getModule();
        Module library = Service.class.getModule();

        System.out.println("reads=" + client.canRead(library));
        System.out.println("api exported="
                + library.isExported("com.acme.library.api", client));

        boolean declaredInternalExport = library.getDescriptor().exports().stream()
                .anyMatch(e -> e.source().equals("com.acme.library.internal"));
        System.out.println("internal declared export=" + declaredInternalExport);
        System.out.println("internal runtime exported="
                + library.isExported("com.acme.library.internal", client));
        System.out.println("internal open="
                + library.isOpen("com.acme.library.internal", client));

        System.out.println("greet=" + Service.greet());

        Class<?> secretType = Class.forName("com.acme.library.internal.Secret");
        Constructor<?> ctor = secretType.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object secret = ctor.newInstance();

        Field field = secretType.getDeclaredField("token");
        field.setAccessible(true);
        System.out.println("token=" + field.get(secret));
    }
}
~~~

### 5.2. Biên dịch và chạy

Trong thư mục chứa src, chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.library,com.acme.client
java --module-path mods --module com.acme.client/com.acme.client.Main
~~~

Cú pháp trên không phụ thuộc glob mở rộng file của shell; có thể chạy tương tự trong terminal Windows PowerShell và các shell phổ biến khác. **--module-source-path src** cho javac biết layout nhiều module, **-d mods** đặt output vào thư mục mods, **-m** chọn module cần compile, còn **--module-path mods** và **--module name/package.Main** xác định module/class để chạy.

Stdout, đã kiểm tra thực tế khi biên dịch mã nguồn với **--release 17** và chạy bằng JDK 21:

~~~text
reads=true
api exported=true
internal declared export=false
internal runtime exported=true
internal open=true
greet=hello
token=hidden
~~~

### 5.3. Vì sao có thể đọc private field?

- **reads=true**: client khai báo requires library.
- **api exported=true**: library exports com.acme.library.api, nên import và gọi Service.greet() thành công.
- **internal declared export=false**: module-info.java không khai báo exports cho package internal.
- **internal runtime exported=true**: Java Module API xem package đã **opens to client** như exported **tại runtime** đối với client. Giá trị này không có nghĩa compiler cho import Secret.
- **internal open=true**: client được mở Reflection sâu vào package internal. Constructor và private field cần setAccessible(true) để vượt qua kiểm tra truy cập Java/JPMS.
- **token=hidden**: sau khi được phép, Field.get() đọc private instance field trên đối tượng Secret.

Nếu bạn thêm dòng import com.acme.library.internal.Secret; vào Main.java, javac không chấp nhận vì package chỉ opens, **không exports**. Đoạn code đang chạy không dùng import này; nó tải class bằng tên và thực hiện Reflection trong phạm vi opens đã cho phép.

## 6. Thử thay đổi quyền và dự đoán lỗi

### Trường hợp A: có requires nhưng thiếu exports API

Đổi module-info.java của library thành:

~~~java
module com.acme.library {
    opens com.acme.library.internal to com.acme.client;
}
~~~

Khi biên dịch lại cùng Main.java, import com.acme.library.api.Service bị từ chối vì package api không exported. Giữ requires trong client **không đủ**. Cách đúng là khôi phục exports com.acme.library.api hoặc đổi kiến trúc sao cho client không phải tham chiếu trực tiếp API đó.

### Trường hợp B: có exports API nhưng thiếu opens internal

Đổi module-info.java của library thành:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Mã nguồn Main vẫn compile (vì nó không import internal.Secret). Nhưng khi chạy và đến ctor.setAccessible(true), JVM không cho client mở quyền constructor của class nằm trong package internal chưa được opens cho client, nên sẽ có **java.lang.reflect.InaccessibleObjectException**. Khôi phục opens ... to com.acme.client, hoặc cấp quyền mở có phạm vi thích hợp khi khởi chạy.

### Trường hợp C: exports internal nhưng không opens internal

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.internal;
}
~~~

Client có thể dùng public API của Secret từ Java code thông thường, nhưng **không thể tùy ý đọc private field token** bằng Field.setAccessible(true). Muốn Reflection vào private members từ module khác thì cần opens (hoặc cơ chế quyền khác hợp lệ). Đây là khác biệt căn bản giữa exports và opens.

### Trường hợp D: opens không có to

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.internal;
}
~~~

Bất kỳ module nào đủ điều kiện thực hiện Reflection ở runtime đều có thể yêu cầu deep reflection đối với package internal. Chỉ mở rộng như vậy khi cần; với framework đã biết tên module, **opens ... to framework.module** diễn đạt ranh giới quyền rõ hơn.

## 7. Thay đổi quyền ở runtime với --add-reads, --add-exports, --add-opens

Trong quá trình chuyển ứng dụng cũ sang JPMS, đôi lúc cần các tùy chọn launcher/compiler để điều chỉnh module graph và khả năng truy cập:

| Tùy chọn | Ý nghĩa chính | Điều không giải quyết |
| --- | --- | --- |
| --add-reads A=B | Cho module A đọc module B | Không tự exports hay opens package của B |
| --add-exports A/p=B | Cho B quyền truy cập public API trong package p của A | Không cho Reflection vào private members |
| --add-opens A/p=B | Mở package p của A cho deep reflection từ B | Không biến package thành API import trực tiếp khi compile mã nguồn |

Ví dụ nếu thư viện đã biên dịch không có opens phù hợp, có thể thử một lần với tùy chọn **runtime**:

~~~bash
java --module-path mods --add-opens com.acme.library/com.acme.library.internal=com.acme.client --module com.acme.client/com.acme.client.Main
~~~

Câu lệnh cho phép module com.acme.client deep-reflect package internal mà không sửa class/module-info đã biên dịch. Trong ví dụ gốc, opens đã được khai báo nên tùy chọn này **không cần thiết**. Nếu thử Trường hợp B (gỡ opens khỏi module-info), tùy chọn trên sẽ khôi phục quyền Reflection.

Đối với ứng dụng trên classpath, nhóm code đó thuộc *unnamed module*; tên đích đặc biệt **ALL-UNNAMED** dùng để mở cho các unnamed modules, chẳng hạn --add-opens java.base/java.lang=ALL-UNNAMED. Tuy nhiên không nên mở bừa package của JDK hay toàn ứng dụng: hãy xác định đúng module caller, đúng package và lý do cần deep reflection. Từ Java 17, việc truy cập nội bộ JDK bị đóng gói mạnh hơn; lỗi InaccessibleObjectException là dấu hiệu nên ưu tiên API public hoặc cấu hình opens có chủ đích.

Với **--add-exports** phục vụ import trực tiếp, đôi khi cần cấu hình phù hợp **cả lúc biên dịch và khi chạy**; một thay đổi runtime không tự sửa lỗi javac ở bước compile. Tùy chọn **--add-opens** hướng đến kiểm tra Reflection runtime, không thay thế exports để compile import.

## 8. Readability có liên quan gì đến Reflection?

Thông thường, Java source cần module readability cùng exports để tham chiếu một public class bên ngoài. Reflection có đặc tính riêng: khi kiểm tra access của các đối tượng reflective, API **giả định readability**; đó là lý do có thể tra cứu class bằng tên và dùng Reflection trong một số trường hợp mà source code không import được. Nhưng Reflection **không bỏ qua module encapsulation**: package phải exports phù hợp cho public access hoặc opens phù hợp khi muốn deep reflection.

Ví dụ này cố ý khai báo requires trong client để đường phụ thuộc rõ ràng; Class.forName không phải biện pháp thay thế module configuration cho phần mã nguồn phụ thuộc thư viện.

Mở package bằng opens thường cần thiết cho các kỹ thuật như Field.setAccessible(true), Constructor.setAccessible(true), Method.setAccessible(true) và MethodHandles.privateLookupIn khi module caller khác module chứa type. API Module.isOpen(package, callerModule) là phép kiểm tra hữu ích để chẩn đoán.

Đừng nhầm việc **tìm thấy** một Field/Method qua getDeclared... với việc **được phép gọi** nó. getDeclaredMethods() có thể liệt kê private members, nhưng invoke/get/set hoặc setAccessible vẫn phải tuân thủ quy định truy cập.

## 9. Quy trình chẩn đoán lỗi module khi dùng Reflection

1. **Xác định module caller thực sự:** nơi thực hiện setAccessible/MethodHandles lookup, có thể là module của framework chứ không phải module ứng dụng. Dùng SomeClass.class.getModule() hoặc thông tin stack trace.
2. **Xác định module chứa lớp và package:** targetClass.getModule(), targetClass.getPackageName(). Đừng nhầm package của class với tên module.
3. **Kiểm tra readability và exports:** moduleCaller.canRead(moduleTarget) giúp phân tích dependency; package có export phù hợp nếu cần dùng public API từ mã nguồn.
4. **Kiểm tra opens đúng caller:** moduleTarget.isOpen(packageName, moduleCaller) phải phù hợp khi cần private reflective access.
5. **Đối chiếu module-info.java với thực tế runtime:** dùng Module.getDescriptor().exports()/opens() để xem khai báo và nhớ rằng Module.isExported có thể true khi opens tại runtime.
6. **Sửa đúng phạm vi:** ưu tiên khai báo exports cho API thật sự public, opens ... to framework cho data binding/serialization, hoặc API public thay thế. Chỉ dùng launcher flags có mục tiêu khi cần tương thích hoặc kiểm chứng nguyên nhân.

**Ví dụ nhanh:** lỗi “module A does not 'opens p' to module B” chỉ ra B là module thực hiện Reflection; thêm requires A ở B **không** cấp quyền mở private field trong p. Cần xem xét opens p to B ở A hoặc cấu hình runtime tương ứng.

## 10. Sai lầm thường gặp và bài tập tự kiểm tra

- **“requires cho phép dùng mọi package”:** sai, phải xét exports và visibility; private Reflection còn cần opens.
- **“exports cũng cho setAccessible vào private”:** sai. exports phục vụ truy cập thành viên public theo luật Java; opens dành cho deep reflection.
- **“opens cho phép import tại compile time”:** sai. Opens là quyền Reflection/runtime, exports mới công khai API với javac.
- **“Module.isExported true chắc chắn có exports trong module-info.java”:** sai khi package được opens cho caller. Kiểm tra ModuleDescriptor.exports() nếu muốn xác nhận khai báo exports.
- **“Mở com.example.model cũng mở com.example.model.internal”:** sai; mỗi package có ranh giới riêng.
- **“Có thể luôn gọi setAccessible(true) vì member đã tìm được”:** sai, đặc biệt với named modules.
- **“Dùng --add-opens ở mọi nơi sẽ giải quyết modularity”:** cấu hình quá rộng che vấn đề thiết kế API, khó bảo trì và tăng phạm vi truy cập nội bộ.

Tự kiểm tra ba tình huống:

1. Module A requires B, nhưng package b.internal của B không exports. A có thể import b.internal.Secret không? **Không**; A đọc B nhưng không được B exports package đó.
2. B exports b.api, không opens b.api. A có thể gọi public method trên public class trong b.api nếu requires B? **Có**. A có thể dùng setAccessible(true) để truy cập private field của class đó không? **Không**, trừ khi có quyền truy cập hợp lệ khác.
3. B opens b.entity to framework.orm, không exports b.entity. Module framework.orm có thể dùng private reflection với b.entity khi đúng API và quyền mở? **Có**. Module app khác có thể import b.entity.Entity trong source của mình chỉ dựa trên opens đó không? **Không**.

**Ghi nhớ:** **requires** tạo quan hệ đọc module, **exports** cung cấp API public giữa module, **opens** cấp quyền Reflection sâu cho package. Ba yếu tố cần được kiểm tra **riêng**, nhất là khi gọi Reflection từ framework trong module khác.

### Tài liệu tham khảo

- JLS 17 — §7.7 Module Declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7
- Java SE 17 — Class Module API (canRead/isExported/isOpen): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 — AccessibleObject API và setAccessible: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- JEP 261 — Module System: https://openjdk.org/jeps/261
- JEP 403 — Strongly Encapsulate JDK Internals: https://openjdk.org/jeps/403
