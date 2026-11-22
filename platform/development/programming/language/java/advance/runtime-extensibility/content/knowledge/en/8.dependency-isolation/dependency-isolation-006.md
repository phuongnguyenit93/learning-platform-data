# Ràng buộc nạp lớp, package lúc chạy và truy cập thành viên không public

## 1. Vì sao cùng tên package vẫn có thể không truy cập được?

Khi thiết kế plugin Java, một tình huống dễ gây nhầm lẫn là hai lớp đều khai báo:

\`\`\`java
package com.example.shared;
\`\`\`

nhưng một lớp nằm trong ứng dụng chủ (host) và lớp kia được nạp bởi \`ClassLoader\` riêng của plugin. Dù tên package giống nhau, JVM có thể coi chúng thuộc **hai runtime package khác nhau**. Vì vậy thành viên có quyền truy cập mặc định (*package-private*) hoặc một số truy cập \`protected\` có thể thất bại ngay cả khi mã nguồn trông như nằm trong cùng package.

Nguyên tắc trung tâm trong cơ chế JVM: **runtime package được xác định bằng tên package và class loader định nghĩa lớp**. Trong môi trường module, quyền truy cập còn chịu ràng buộc của Java Platform Module System (JPMS), chẳng hạn \`exports\`, \`opens\` và quan hệ module. Không thể chỉ đổi chuỗi \`package\` hoặc đường dẫn JAR để vượt ranh giới đó.

Bài này tập trung vào tương tác giữa cách nạp lớp, danh tính runtime package và kiểm tra quyền truy cập thành viên không \`public\`; đặc biệt hữu ích khi host và plugin cố tình cô lập các dependency bằng nhiều class loader.

## 2. Danh tính lớp và runtime package

### 2.1. Class identity

Ở JVM, mỗi lớp được định danh bởi:

1. **Binary name**, ví dụ \`com.example.api.Contract\`.
2. **Defining class loader**: loader thực sự gọi cơ chế định nghĩa lớp đó.

Do đó hai class loader khác nhau có thể định nghĩa hai lớp có cùng binary name nhưng JVM vẫn coi là hai kiểu khác nhau. Hậu quả có thể là \`ClassCastException\`, \`LinkageError\` hoặc lỗi kiểm tra quyền truy cập tùy cách sử dụng và ràng buộc nạp lớp.

Phân biệt các vai trò:

- **Initiating loader**: loader được yêu cầu tìm/nạp lớp; có thể ủy quyền cho loader cha.
- **Defining loader**: loader thực sự định nghĩa \`Class\` từ bytecode.
- **Parent delegation**: cơ chế thường dùng để ưu tiên class do loader cha cung cấp. Hai plugin loader cùng ủy quyền API cho parent có thể nhìn thấy đúng **một** \`Contract.class\`.

Trong bài này, ranh giới runtime package dựa vào **defining loader**, không chỉ loader được truyền vào \`Class.forName\` hoặc đường dẫn class path xuất hiện trong cấu hình.

### 2.2. Runtime package

Xét hai lớp:

\`\`\`text
HostClass    package com.example.shared;  defining loader = L1
PluginClass  package com.example.shared;  defining loader = L2
\`\`\`

Nếu \`L1 != L2\`, hai lớp nằm ở **hai runtime package khác nhau**, mặc dù cùng tên package. Điều này ảnh hưởng tới khả năng truy cập:

| Thành viên/kiểu | Điều kiện quan trọng trong class path truyền thống |
|---|---|
| \`public\` class, \`public\` member | Có thể truy cập nếu lớp khai báo nhìn thấy được và không bị chính sách module cản trở |
| \`private\` | Chỉ truy cập theo quy tắc cùng lớp/nest, không trở thành truy cập tự do vì cùng package |
| Không ghi modifier (package-private) | Chỉ truy cập trong **cùng runtime package** |
| \`protected\` | Cho phép cùng runtime package; hoặc theo quy tắc subclass cùng các hạn chế của truy cập \`protected\` |
| Package-private top-level class | Không thể tự động dùng từ plugin loader chỉ vì cùng tên package |

Một lớp Java có thể được biên dịch hợp lệ vì compiler thấy các source trong cùng package, nhưng khi chạy dưới các loader khác nhau, JVM kiểm tra quyền theo runtime package thực tế và có thể ném \`IllegalAccessError\`.

## 3. Package-private: ví dụ lỗi thực tế

Hãy xét hai source trong cùng package:

**\`host-src/demo/shared/HostSecret.java\`**

\`\`\`java
package demo.shared;

public class HostSecret {
    static String token() {
        return "HOST_TOKEN";
    }
}
\`\`\`

\`token()\` không có modifier nên là **package-private**.

**\`plugin-src/demo/shared/PluginCall.java\`**

\`\`\`java
package demo.shared;

public class PluginCall {
    public static String call() {
        return HostSecret.token();
    }
}
\`\`\`

Khi compile, nếu cả hai lớp được nhìn thấy trên cùng compile classpath và cùng package, \`javac\` chấp nhận lời gọi. Nhưng giả sử khi chạy \`HostSecret\` được parent loader định nghĩa còn \`PluginCall\` được child loader định nghĩa thì dù binary name của package vẫn là \`demo.shared\`, hai lớp không thuộc cùng runtime package.

### 3.1. Bộ ví dụ có thể chạy trên Java 17+

Tạo cấu trúc:

\`\`\`text
demo/
├── host-src/demo/shared/HostSecret.java
├── plugin-src/demo/shared/PluginCall.java
└── Runner.java
\`\`\`

Tệp **\`Runner.java\`**:

\`\`\`java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class Runner {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("build/plugin.jar").toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl},
                Runner.class.getClassLoader())) {
            Class<?> plugin = Class.forName(
                    "demo.shared.PluginCall", true, pluginLoader);

            System.out.println("host loader: "
                    + demo.shared.HostSecret.class.getClassLoader().getClass().getSimpleName());
            System.out.println("plugin loader: "
                    + plugin.getClassLoader().getClass().getSimpleName());

            try {
                System.out.println(plugin.getMethod("call").invoke(null));
            } catch (java.lang.reflect.InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                System.out.println("cause: " + cause.getClass().getSimpleName());
            }
        }
    }
}
\`\`\`

Dùng các lệnh POSIX shell từ thư mục \`demo/\`:

\`\`\`bash
mkdir -p build/host build/plugin build/runner
javac -d build/host host-src/demo/shared/HostSecret.java
javac -cp build/host -d build/plugin plugin-src/demo/shared/PluginCall.java
jar --create --file build/host.jar -C build/host .
jar --create --file build/plugin.jar -C build/plugin .
javac -cp build/host.jar -d build/runner Runner.java
java -cp "build/runner:build/host.jar" Runner
\`\`\`

Đầu ra điển hình của OpenJDK 17 trên class path thông thường:

\`\`\`text
host loader: AppClassLoader
plugin loader: URLClassLoader
cause: IllegalAccessError
\`\`\`

Giải thích:

1. JVM application loader định nghĩa \`HostSecret\` từ \`host.jar\`.
2. \`PluginCall\` chỉ tồn tại trong \`plugin.jar\` mà parent loader không thấy, nên \`URLClassLoader\` định nghĩa lớp plugin.
3. Khi mã plugin thực hiện \`invokestatic HostSecret.token()\`, JVM phát hiện \`token()\` không public và hai lớp không ở cùng runtime package.
4. \`IllegalAccessError\` được ném tại runtime. Reflection ở \`Runner\` chỉ dùng để gọi \`PluginCall.call()\` và bọc exception trong \`InvocationTargetException\`; nguyên nhân gốc là lỗi truy cập trực tiếp trong bytecode plugin.

Tên loại loader trên JVM/launcher khác có thể khác; giá trị cần kiểm chứng là **class loader của hai lớp khác nhau** và \`IllegalAccessError\`.

Nếu chuyển \`HostSecret.token()\` thành \`public static\` rồi biên dịch lại JAR host, lời gọi qua ranh giới loader được phép theo quyền \`public\` trong ví dụ class path này. Nhưng trong JPMS named modules, vẫn phải bảo đảm package được export cho module cần truy cập.

**Điều cần tránh:** Không đưa \`host.jar\` vào \`plugin.jar\` để giữ lại một bản \`HostSecret\` riêng. Cách đó có thể làm biến mất triệu chứng lỗi truy cập nhưng gây chia đôi state/type identity, phá contract và làm hệ thống khó debug.

## 4. Truy cập protected khác package-private ra sao?

Thành viên \`protected\` có hai hướng truy cập quan trọng:

- Các lớp cùng runtime package có thể sử dụng theo quy tắc package.
- Subclass khác runtime package có thể truy cập thành viên inherited được phép, nhưng với instance member thường có điều kiện bổ sung về kiểu của expression mục tiêu; không phải mọi đối tượng của superclass đều là receiver hợp lệ.

Ví dụ về subclass được phép về mặt source:

\`\`\`java
package demo.plugin;

public class PluginChild extends demo.api.Base {
    public String readOwnState() {
        return this.state();
    }
}
\`\`\`

Giả sử \`demo.api.Base\` là public và có:

\`\`\`java
protected String state() {
    return "ready";
}
\`\`\`

Đây là **đoạn minh họa**; phải đặt \`Base\` vào file \`demo/api/Base.java\` trong API JAR và \`PluginChild\` vào file \`demo/plugin/PluginChild.java\` để biên dịch. Access hợp lệ qua \`this\` vì \`PluginChild\` kế thừa từ \`Base\`; không đồng nghĩa code bất kỳ trong package \`demo.plugin\` có thể gọi \`state()\`.

Nếu plugin chỉ đặt cùng package với \`Base\` nhưng loader khác, đường truy cập "cùng package" không có hiệu lực; phải thỏa điều kiện subclass. Với API plugin, thường nên dùng phương thức \`public\` trong contract/interface thay vì dựa vào sự thân thiện của package-private hoặc quy tắc \`protected\` phức tạp.

## 5. Module JPMS bổ sung ràng buộc nào?

Từ Java 9, **named modules** còn có ranh giới truy cập theo module:

- \`requires\` khai báo module phụ thuộc.
- \`exports\` cho phép code ở module khác truy cập **public types** trong package được xuất.
- \`opens\` cho phép deep reflection đối với package được mở, theo phạm vi của module directive.
- \`exports ... to ...\` / \`opens ... to ...\` chỉ áp dụng cho các module đích được chỉ định.

Ví dụ mô tả module API:

\`\`\`java
module demo.api {
    exports demo.api;
}
\`\`\`

Module plugin:

\`\`\`java
module demo.plugin {
    requires demo.api;
}
\`\`\`

Những module declaration trên là **mã minh họa** cần cấu trúc source/class và build module path phù hợp; không phải một chương trình đơn file.

**Cảnh báo trọng tâm:** \`exports\` không biến package-private thành public. Một \`public\` class trong package không exported cũng không có quyền truy cập bình thường từ module khác. \`opens\` cho phép deep reflection trong điều kiện được chỉ định, nhưng không cấp quyền truy cập Java thông thường của bytecode vào package-private member.

JPMS không cho phép dùng tên package trùng một cách tùy tiện giữa các named modules được resolve trong cùng module layer/ClassLoader; cấu trúc "split packages" có thể dẫn tới lỗi module resolution hoặc layer definition. Trong plugin architecture, nên thiết kế package namespace riêng theo module, tránh coi việc cùng tên package là công cụ chia sẻ API.

## 6. Reflection có vượt được ranh giới này không?

Reflection khác với liên kết bytecode thông thường.

Ví dụ Java reflection:

\`\`\`java
var method = someClass.getDeclaredMethod("hidden");
method.setAccessible(true);
Object value = method.invoke(instance);
\`\`\`

Đoạn trên chỉ minh họa API, phụ thuộc vào \`someClass\` và \`instance\` đã tồn tại. Nó không bảo đảm chạy được trong mọi module/class loader. \`setAccessible(true)\` có thể thất bại với \`InaccessibleObjectException\` khi package nằm trong named module không mở theo đúng quan hệ quyền truy cập. Java module encapsulation không được vô hiệu hóa chỉ vì plugin dùng reflection.

Ở class path/unnamed module, nhiều trường hợp deep reflection có thể được cho phép, nhưng cách này làm coupling mạnh vào chi tiết implementation, khó bảo trì và gây rủi ro tương thích. \`MethodHandles.Lookup\` và \`privateLookupIn\` cũng chịu các quy tắc quyền truy cập và module openness riêng; không được coi là cơ chế bypass tự do.

Trong hệ thống plugin, giải pháp bền vững là công khai một API rõ ràng, chuyển capability cần thiết vào contract và truyền dependency qua interface hoặc factory.

## 7. Cô lập dependency và shared API

Một sơ đồ loader điển hình:

\`\`\`text
Bootstrap / Platform
       |
Application loader (parent)
       |-- demo.api.PluginService
       |-- demo.api.PluginContext
       |-- demo.host.Host
       |
       +-- PluginLoader A (child)
       |       |-- demo.vendorA.PluginA
       |       +-- thư viện A phụ thuộc
       |
       +-- PluginLoader B (child)
               |-- demo.vendorB.PluginB
               +-- thư viện B phụ thuộc
\`\`\`

Host và plugins chia sẻ **cùng bản định nghĩa** của interface/API ở parent. Các lớp implementation của plugin nên nằm trong namespace riêng, do child loader sở hữu. Cách bố trí này tránh cố dùng package-private để giao tiếp xuyên loader.

Nếu plugin tự nạp bản \`demo.api.PluginService\` riêng (ví dụ child-first ưu tiên JAR plugin chứa API), host có thể gặp \`ClassCastException\` khi cố ép plugin instance sang \`PluginService\` của host. Cả hai interface cùng tên nhưng defining loader khác nhau nên là các kiểu khác nhau.

**Loading constraints:** JVM áp dụng ràng buộc nhất quán kiểu khi liên kết các phương thức/field có kiểu đi qua ranh giới loader. Một hệ thống cấu hình class loader sai có thể gặp \`LinkageError: loader constraint violation\`, kể cả trước khi xuất hiện thao tác ép kiểu rõ ràng. Nguyên tắc vận hành là giữ các kiểu crossing boundary (interface, DTO, exception chung) trong API dùng chung, không nhân đôi chúng trong plugin loader.

## 8. Sealing và package namespace

**Package sealing** trong JAR manifest là một cơ chế riêng: đặt \`Sealed: true\` yêu cầu các class của package sealed phải được định nghĩa từ code source phù hợp, thường cùng JAR, trong một class loader. Nó ngăn split package từ nhiều JAR cùng loader khi package bị seal.

Nhưng sealing **không** kết hợp hai runtime package ở hai loader thành một package và **không** trao quyền package-private xuyên loader. Thay đổi \`Sealed\` cũng không sửa được \`IllegalAccessError\` ở ví dụ \`HostSecret\` và \`PluginCall\` vì nguyên nhân nằm ở defining loader khác nhau.

Một nguyên tắc hữu ích khi đóng gói plugin:

- Dùng package riêng cho implementation và dependency nội bộ.
- Giữ API chia sẻ trong JAR/module riêng, do loader chung cung cấp.
- Không tạo split package giữa host, contract và plugin.
- Chỉ bật sealing khi muốn enforce nguồn định nghĩa lớp trong một package, sau khi đã kiểm tra cấu trúc JAR và loader.

## 9. Các lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| \`IllegalAccessError\` khi gọi package-private method | Caller và declaring class có cùng tên package nhưng khác defining loader | In \`Class.getClassLoader()\`, kiểm tra runtime package |
| \`ClassCastException\` giữa hai interface cùng tên | Contract bị load hai lần trong các loader khác nhau | Kiểm tra \`api.jar\` ở parent và child, parent delegation |
| \`NoClassDefFoundError\` | Thiếu class dependency hoặc lỗi khi khởi tạo class | Xem full stack trace và runtime classpath |
| \`LinkageError: loader constraint violation\` | Type xuyên boundary bị định nghĩa không nhất quán | Kiểm tra binary names, signatures và loader topology |
| \`InaccessibleObjectException\` ở reflection | Named module chưa \`opens\` package phù hợp | Kiểm tra \`module-info.java\`, \`--add-opens\` chỉ dùng tạm khi hiểu rủi ro |
| \`SecurityException: sealing violation\` | Class cùng package được nạp từ nhiều code sources không hợp lệ | Xem manifest, JAR và defining loader |
| \`IllegalAccessError\` với public class trong named module | Package không exported hoặc module access không hợp lệ | Kiểm tra module readability và \`exports\` |

Không phải lỗi nào cũng do class loader: cần kiểm tra chính xác exception và stack trace trước khi đổi cấu trúc packaging. Ví dụ, \`NoSuchMethodError\` thường liên quan binary incompatibility hơn là package-private.

## 10. Chẩn đoán và kiểm thử

### Quan sát nguồn và loader

Có thể thêm chẩn đoán trong host:

\`\`\`java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("source=" + (type.getProtectionDomain().getCodeSource() == null
            ? "unknown"
            : type.getProtectionDomain().getCodeSource().getLocation()));
}
\`\`\`

Đây là **đoạn tiện ích minh họa** cần đặt trong một lớp Java, có thể gặp security policy trong một số môi trường. \`getModule().getName()\` có thể trả \`null\` đối với unnamed module. Không dựa vào tên hiển thị của loader làm ID tuyệt đối; so sánh chính các đối tượng loader trong môi trường debug.

Trên JVM HotSpot hiện đại, có thể dùng:

\`\`\`bash
java -Xlog:class+load=info -cp "build/runner:build/host.jar" Runner
\`\`\`

Thông tin class loading hỗ trợ xác định lớp lấy từ JAR nào. Khi debug có nhiều plugin loader, nên kết hợp log, \`Class.getClassLoader()\`, code source, module và đồ thị phụ thuộc.

### Checklist kiểm thử plugin

1. **Compile** plugin chỉ dựa vào contract API công khai; không dùng package-private member của host.
2. **Runtime** kiểm tra API được parent loader định nghĩa một lần, implementation được child loader định nghĩa đúng ý định.
3. **Dependency isolation** chạy đồng thời hai plugin dùng thư viện nội bộ khác phiên bản để kiểm tra xung đột.
4. **Access control** có test xác nhận lời gọi public API thành công và truy cập không hợp lệ bị chặn.
5. **Module mode** nếu dùng JPMS, kiểm thử cả \`requires\`, \`exports\`, \`opens\`, package name và module layer.
6. **Packaging** kiểm tra JAR không vô ý nhúng duplicate contract, split package hoặc cấu hình sealing mâu thuẫn.

## 11. Kết luận

Tên package là một phần của namespace Java, nhưng runtime package còn phụ thuộc **defining class loader**. Đặt plugin và host vào cùng tên package không tạo được quan hệ truy cập package-private khi chúng được định nghĩa bởi các loader khác nhau. Muốn hai bên giao tiếp ổn định, hãy thiết kế hợp đồng \`public\` được chia sẻ bởi một loader chung, kiểm soát module exports khi dùng JPMS, và để các lớp implementation/dependency của mỗi plugin trong namespace riêng. Điều này làm việc cô lập dependency khả thi mà không dựa vào các đặc quyền truy cập dễ bị phá vỡ lúc chạy.
