# Nhận diện kiểu bằng tên nhị phân và class loader định nghĩa trong Java

Trong Java, hai file `.class` có **cùng tên package, cùng tên lớp, thậm chí cùng từng byte mã máy Java** vẫn có thể là **hai kiểu runtime khác nhau**. Ngược lại, hai lời gọi nạp lớp đi qua **hai đối tượng `ClassLoader` khác nhau** vẫn có thể cùng trả về **một kiểu duy nhất** nếu cả hai ủy quyền cho cùng loader đã định nghĩa lớp đó.

Quy tắc cốt lõi của Java Virtual Machine Specification (JVMS `5.3) đối với class/interface thông thường là:

~~~text
Định danh kiểu runtime = (binary name, defining class loader)
~~~

Hai thành phần phải được xét **cùng nhau**. Một tên chuỗi, một vị trí JAR, phiên bản thư viện hoặc một đối tượng class loader đang tham gia tìm kiếm đều không tự quyết định type identity. Đây là nền tảng để hiểu vì sao hệ thống plugin có thể đồng thời nạp nhiều phiên bản thư viện, và vì sao đôi khi xảy ra `ClassCastException` kiểu “lớp X không thể ép thành lớp X”.

## 1. Binary name là tên gì?

**Binary name** là tên mà JVM dùng để nhận diện class/interface trong cấu trúc bytecode và lời gọi nạp lớp. Với class/interface thông thường (không phải array hoặc hidden class), `Class.getName()` trả về binary name.

| Loại khai báo | Tên thể hiện trong nguồn | Binary name điển hình |
| --- | --- | --- |
| Class top-level | `package demo.api; class Service {}` | `demo.api.Service` |
| Interface top-level | `package demo.api; interface Plugin {}` | `demo.api.Plugin` |
| Member class | `class Outer { static class Inner {} }` | `demo.api.Outer$Inner` |
| Nested interface | `Outer.Nested` | `demo.api.Outer$Nested` |
| Class trong package mặc định | `class Example {}` | `Example` |

Ký tự `$` trong tên class thành viên rất quan trọng: `Class.forName("demo.api.Outer.Inner")` không thay thế được `Class.forName("demo.api.Outer$Inner")`. Những tên local/anonymous class có thể chứa ký hiệu do compiler sinh ra và không nên được coi là API ổn định.

Ba khái niệm cần phân biệt:

- **Simple name**: tên ngắn, ví dụ `Inner`, có thể trùng ở nhiều package.
- **Canonical name**: tên dùng để chỉ class ở cấp ngôn ngữ nếu tồn tại, ví dụ `demo.api.Outer.Inner`; không đồng nhất với binary name của member class.
- **Binary name**: ví dụ `demo.api.Outer$Inner`, dùng khi gọi `ClassLoader.loadClass(String)` hay `Class.forName(String, boolean, ClassLoader)` với class thông thường.

Trên class file, đường dẫn tài nguyên thường là `demo/api/Service.class`, nhưng chuỗi truyền cho `loadClass` là `demo.api.Service`. Không nên dùng đường dẫn có dấu `/` làm tên lớp khi gọi API này.

**Ngoại lệ đáng biết:** `String[].class.getName()` trả về `[Ljava.lang.String;`, còn `int[].class.getName()` trả về `[I`. Đó là cú pháp tên của array class, không phải dạng binary name top-level thông thường. `int.class` là primitive type, không có file `int.class` để custom loader tự định nghĩa. Hidden classes được định nghĩa bằng API chuyên dụng cũng có quy tắc tên và tra cứu riêng; `Class.forName` không phải cơ chế tìm hidden class bằng tên.

## 2. Defining loader khác initiating loader

Đây là sự phân biệt quan trọng nhất của chủ đề.

- **Defining class loader** là loader thực sự **định nghĩa** class/interface từ biểu diễn nhị phân, thường qua cơ chế `defineClass(...)`. Với lớp thông thường do user-defined loader định nghĩa, `SomeClass.class.getClassLoader()` cho biết loader đó. Class do bootstrap loader nạp thường trả `null`.
- **Initiating class loader** là loader **bắt đầu** một yêu cầu tải lớp. Nó có thể tự định nghĩa lớp, hoặc ủy quyền cho loader khác rồi nhận lại cùng đối tượng `Class<?>`. Một class có thể được ghi nhận là đã được initiate bởi nhiều loader, nhưng vẫn chỉ có một defining loader cho chính class đó.

Quy trình chuẩn của `ClassLoader.loadClass(name, resolve)`, trừ khi bị subclass tùy biến, là:

~~~text
L.loadClass("demo.lib.Widget")
    |
    +-- findLoadedClass(name): L từng tải lớp tên này chưa?
    |
    +-- parent.loadClass(name): yêu cầu cha trước
    |       |
    |       +-- nếu cha tìm thấy: trả về Class do cha/ancestor định nghĩa
    |
    +-- findClass(name): nếu cha không tìm được, L thử tự tìm và định nghĩa
            |
            +-- defineClass(...) -> Class do L định nghĩa
~~~

Đó là nguyên tắc **parent-first delegation** của triển khai mặc định. `URLClassLoader` cũng tuân theo hành vi này nếu không bị can thiệp. Custom class loader có thể xây dựng chiến lược khác (chẳng hạn child-first cho package plugin riêng), nhưng phải bảo đảm quy tắc JVM, tính nhất quán kiểu và ranh giới API.

Hệ quả:

~~~java
Class<?> value = Class.forName("demo.lib.Widget", false, childLoader);
ClassLoader defining = value.getClassLoader();
~~~

`childLoader` là **loader được yêu cầu bắt đầu tìm**, chưa chắc là `defining`. Nếu child ủy quyền cho parent và parent đã có `demo.lib.Widget`, thì `defining` chính là parent. Tham số `false` ở `Class.forName(name, initialize, loader)` chỉ có nghĩa **không yêu cầu khởi tạo class ngay lúc đó**; nó không khẳng định mọi hoạt động loading/linking đều chưa diễn ra.

Ví dụ hai loader `left` và `right` khác nhau nhưng đều hỏi parent thành công:

~~~text
left.loadClass("demo.lib.Widget")  ---+
                                      +--> parent-defined Widget.class
right.loadClass("demo.lib.Widget") ---+
~~~

Kết quả có thể là `leftResult == rightResult`. Vì vậy câu “hai class loader khác nhau nên chắc chắn hai kiểu khác nhau” là **sai nếu hai loader chỉ đang ủy quyền**.

## 3. Cách xét hai kiểu runtime có thực sự trùng nhau

Đối với class/interface thông thường, ta có bảng:

| Binary name | Defining loader | Kết luận type identity |
| --- | --- | --- |
| Khác nhau | Bất kỳ | Hai kiểu khác nhau |
| Giống nhau | Cùng một defining loader | Cùng một kiểu runtime (cùng đối tượng `Class` trong JVM) |
| Giống nhau | Hai defining loader khác nhau | **Hai kiểu khác nhau** dù mã nguồn/bytecode giống nhau |
| Giống nhau | Hai initiating loader khác nhau, cùng delegate về một defining loader | **Vẫn cùng kiểu** |

Trong Java, cách đơn giản và chính xác nhất để so sánh danh tính kiểu **đã được nạp** là:

~~~java
boolean sameRuntimeType = a == b;  // a, b là Class<?>.
~~~

Không dùng `a.getName().equals(b.getName())` thay cho phép so sánh trên. Hai tên bằng nhau chỉ chứng minh cùng **tên**, không chứng minh cùng **kiểu**.

Dấu hiệu định danh khác nhau ảnh hưởng trực tiếp đến:

- **`instanceof`/`Class.isInstance` và cast**: instance tạo từ loại A không tự động gán được cho loại B chỉ vì hai lớp có cùng chuỗi tên.
- **Reflection**: tham số kiểu cho `getMethod`, `getDeclaredMethod`, `Method.invoke` phải tương thích theo `Class` thực tế; chữ ký viết cùng tên chuỗi ở hai loader không làm hai kiểu trở nên bằng nhau.
- **Field/method signatures và liên kết bytecode**: JVM có các loader constraints để giữ tính nhất quán kiểu trong quan hệ kế thừa và phương thức được liên kết; vi phạm có thể dẫn tới `LinkageError`.
- **Runtime package access**: package runtime của class/interface được xác định từ **tên package và defining loader**. Hai class đều khai báo `package demo.spi;` nhưng do hai defining loader khác nhau định nghĩa không phải là thành viên cùng một runtime package; không vì chuỗi package giống nhau mà được quyền package-private qua ranh giới đó.
- **Cache/registry theo lớp**: dùng chuỗi binary name làm khóa duy nhất trên một hệ thống đa loader có thể va chạm. Nếu đã có `Class<?>`, dùng chính đối tượng đó làm khóa khi phù hợp với vòng đời; nếu lưu lâu dài cần tính đến nguy cơ giữ mạnh class loader cũ.

### “Cùng class file” có bảo đảm giống kiểu?

Không. Bytecode giống nhau là điều kiện về **nội dung**, không phải điều kiện về **định danh runtime**. Hai URLClassLoader riêng biệt có thể cùng đọc một thư mục chứa một file `.class` và mỗi loader đều định nghĩa lớp riêng. JVM xem hai `Class` kết quả là hai kiểu khác nhau.

### “Cùng class loader” có đủ không?

Nếu nói đúng **defining loader** và cùng **binary name của class/interface**, thì có. Một JVM không cho một loader định nghĩa lại cùng một binary name thành hai class thông thường độc lập. Nếu nói “cùng loader mà tôi gọi qua `loadClass`”, đây có thể chỉ là initiating loader, nên phải nhìn vào `Class.getClassLoader()` của kết quả.

## 4. Ví dụ Java 17 đầy đủ: hai loader định nghĩa cùng một tên lớp

Mục tiêu của ví dụ là chứng minh một tình huống kiểm soát được:

1. Host chia sẻ một interface `demo.api.Action`.
2. Plugin có một class `demo.plugin.ActionImpl`; host **không** đưa class này vào classpath cha.
3. Host tạo **hai URLClassLoader độc lập** cùng trỏ đến thư mục chứa `ActionImpl.class`.
4. Mỗi URLClassLoader phải tự định nghĩa `ActionImpl` vì parent không thấy class đó.
5. Hai class cùng binary name nhưng khác runtime identity; instance vẫn dùng được qua interface API chung.

Cây thư mục ban đầu:

~~~text
src/
└── demo/
    ├── api/
    │   └── Action.java
    ├── plugin/
    │   └── ActionImpl.java
    └── host/
        └── ClassIdentityDemo.java
~~~

### 4.1. Interface công khai do host sở hữu

Tệp `src/demo/api/Action.java`:

~~~java
package demo.api;

public interface Action {
    String run();
}
~~~

Trong kiến trúc plugin, API chung phải được định nghĩa một lần ở ranh giới được host và plugin cùng nhìn thấy. Ở ví dụ này, `Action.class` được nạp từ classpath ứng dụng. Hai plugin loader dùng loader của chính `Action` làm parent để nhìn thấy cùng một đối tượng `Class` của interface.

### 4.2. Triển khai nằm riêng trong plugin

Tệp `src/demo/plugin/ActionImpl.java`:

~~~java
package demo.plugin;

import demo.api.Action;

public final class ActionImpl implements Action {
    @Override
    public String run() {
        return "ready";
    }
}
~~~

Class này được biên dịch vào thư mục `out-plugin` riêng, không đưa `out-plugin` vào classpath khi chạy host. Hai loader đều nhìn thấy bytecode từ cùng thư mục, nhưng mỗi loader có vùng tên runtime riêng cho lớp do chính nó định nghĩa.

### 4.3. Host khám phá và đối chiếu kiểu

Tệp `src/demo/host/ClassIdentityDemo.java`:

~~~java
package demo.host;

import demo.api.Action;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ClassIdentityDemo {
    private static final String NAME = "demo.plugin.ActionImpl";

    public static void main(String[] args) throws Exception {
        URL url = Path.of("out-plugin").toAbsolutePath().toUri().toURL();
        ClassLoader apiLoader = Action.class.getClassLoader();

        try (URLClassLoader left = new URLClassLoader("plugin-left", new URL[]{url}, apiLoader);
             URLClassLoader right = new URLClassLoader("plugin-right", new URL[]{url}, apiLoader)) {
            Class<?> a = Class.forName(NAME, false, left);
            Class<?> b = Class.forName(NAME, false, right);

            System.out.println("binary names equal: " + a.getName().equals(b.getName()));
            System.out.println("Class objects identical: " + (a == b));
            System.out.println("defining loaders different: " + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("left defined by left: " + (a.getClassLoader() == left));
            System.out.println("right defined by right: " + (b.getClassLoader() == right));
            System.out.println("shared API: " + (Action.class.isAssignableFrom(a)
                    && Action.class.isAssignableFrom(b)));

            Object instanceB = b.getDeclaredConstructor().newInstance();
            System.out.println("left accepts right instance: " + a.isInstance(instanceB));
            System.out.println("as common API: " + ((Action) instanceB).run());

            try {
                a.cast(instanceB);
                System.out.println("cross cast succeeded");
            } catch (ClassCastException expected) {
                System.out.println("cross cast: ClassCastException");
            }
        }
    }
}
~~~

**Giải thích lựa chọn quan trọng:**

- `Class.forName(NAME, false, left/right)` dùng **cùng binary name** ở cả hai lần tải; kết quả là hai đối tượng `Class`. Cờ `false` tránh yêu cầu class initialization ngay tại bước tra cứu.
- `Action.class.getClassLoader()` được dùng làm parent cho cả hai URLClassLoader, nên phần API chung không bị copy hai lần.
- `out-plugin` chỉ nằm trong URL tìm kiếm riêng của mỗi loader, không nằm trên host classpath. Điều này bảo đảm loader cha không tải `ActionImpl` trước rồi làm phép thử mất ý nghĩa.
- `a.isInstance(instanceB)` kiểm tra liệu instance từ loader phải có thuộc kiểu mà loader trái định nghĩa hay không. Kết quả `false` không phụ thuộc vào việc mã bytecode có giống nhau.
- `(Action) instanceB` thành công vì cả hai implementation cùng trỏ đến **một** kiểu `Action` được chia sẻ.
- `a.cast(instanceB)` ném `ClassCastException` vì `a` và `b` là hai kiểu runtime riêng, dù cùng tên chuỗi.

### 4.4. Biên dịch Java 17 và chạy

Từ thư mục chứa `src`, dùng PowerShell trên Windows:

~~~powershell
javac --release 17 -d out-api src/demo/api/Action.java
javac --release 17 -cp out-api -d out-plugin src/demo/plugin/ActionImpl.java
javac --release 17 -cp out-api -d out-host src/demo/host/ClassIdentityDemo.java
java -cp "out-api;out-host" demo.host.ClassIdentityDemo
~~~

Trên Linux/macOS, chỉ thay dấu phân tách classpath ở lệnh `java` bằng dấu hai chấm:

~~~bash
java -cp "out-api:out-host" demo.host.ClassIdentityDemo
~~~

Nhớ **không thêm `out-plugin` vào `-cp`** của host cho lần chạy chính; mã host tìm plugin qua hai URLClassLoader. Thư mục làm việc khi chạy phải là nơi có `out-plugin` vì code đang gọi `Path.of("out-plugin")`.

Stdout chính xác (đã biên dịch với `--release 17` và kiểm tra trên JVM):

~~~text
binary names equal: true
Class objects identical: false
defining loaders different: true
left defined by left: true
right defined by right: true
shared API: true
left accepts right instance: false
as common API: ready
cross cast: ClassCastException
~~~

Đây là bằng chứng trực tiếp: `a.getName().equals(b.getName())` là `true`, nhưng `a == b` là `false`; defining loader khác nhau. Các instance không tương thích theo lớp implementation, trong khi hợp đồng interface chung vẫn sử dụng được.

### 4.5. Thử nghiệm ngược: hai loader nhưng chỉ một kiểu

Trong cùng thư mục ví dụ, nếu cố ý đưa thêm `out-plugin` vào classpath của host:

~~~powershell
java -cp "out-api;out-host;out-plugin" demo.host.ClassIdentityDemo
~~~

thì parent class loader giờ nhìn thấy `demo.plugin.ActionImpl`. Do `URLClassLoader` mặc định parent-first, cả `left` và `right` có thể ủy quyền tìm thấy **cùng `Class` do parent định nghĩa**. Trong điều kiện mẫu này, dự kiến `Class objects identical: true`, `defining loaders different: false` và `a.cast(instanceB)` thành công; riêng hai dòng `left defined by left`/`right defined by right` sẽ là `false`.

Thử nghiệm đó giải thích vì sao chỉ “tạo hai loader” chưa đủ để khẳng định sẽ có hai kiểu. Phải kiểm soát **đường nạp, parent classpath và nơi thực tế định nghĩa class**.

## 5. Tác động đến hệ thống plugin và hợp đồng SPI

Một kiến trúc plugin phổ biến có dạng:

~~~text
Host / application loader
    |
    +-- shared API: demo.api.Action
    |       (một định danh kiểu chung)
    |
    +-- plugin loader A
    |       +-- demo.plugin.ActionImpl  -> type A
    |
    +-- plugin loader B
            +-- demo.plugin.ActionImpl  -> type B

type A != type B
type A implements shared Action
type B implements shared Action
~~~

Nếu vô tình đóng gói `demo.api.Action` vào mỗi plugin và dùng chiến lược child-first nạp luôn API của từng plugin, lúc đó host, plugin A, plugin B có thể có **ba `Class` riêng cho cùng binary name `demo.api.Action`**. Host nhận một object và cố ép sang `Action` của mình có thể thất bại, hoặc `ServiceLoader` báo provider “not a subtype” do service interface không cùng type identity.

**Quy tắc kiến trúc:**

1. Đặt **service interface, DTO và các type đi qua ranh giới host–plugin** ở class loader dùng chung (thường là cha của plugin loaders).
2. Tách code implementation và dependency riêng của plugin để mỗi plugin loader sở hữu chúng khi cần cô lập.
3. Không để implementation class của plugin trở thành kiểu tham số/giá trị trả về mà host bắt buộc phải ép trực tiếp. Giao tiếp qua interface/DTO chung.
4. Khi một plugin được nạp lại, phiên bản mới có thể là một kiểu runtime mới dù binary name y hệt. Không ép object của phiên bản cũ sang implementation class của phiên bản mới.
5. Registry lưu cấu trúc metadata của plugin (ID, version, nguồn, loader/lifecycle); đừng dùng riêng `getName()` làm khóa duy nhất nếu các plugin có thể định nghĩa class trùng tên.

**Giới hạn:** tên giống nhau không tự có nghĩa hai plugin thực thi giống nhau; đồng thời tên khác nhau không tự nói lên khả năng tương thích về service. Hợp đồng API và type identity đều quan trọng.

## 6. Runtime package và ranh giới truy cập

Theo JVMS, runtime package được xác định bởi **package name + defining class loader**. Xét:

~~~text
Loader A -> package demo.internal; class Helper
Loader B -> package demo.internal; class Bridge
~~~

Dù cùng ghi `package demo.internal;`, hai class trên thuộc **hai runtime package khác nhau** nếu chúng do loader A và loader B định nghĩa. Không thể suy luận rằng `Bridge` được truy cập thành viên package-private của `Helper` chỉ nhờ chuỗi package giống nhau.

Nếu bytecode tạo liên kết truy cập trái phép, JVM có thể phát sinh `IllegalAccessError` trong quá trình resolve/link thực tế. Trường hợp báo lỗi có thể phụ thuộc kiểu liên kết và thời điểm JVM kiểm tra; nên chẩn đoán dựa trên actual defining loaders thay vì chỉ nhìn source package.

Trong JPMS, `Module` và `ModuleLayer` ảnh hưởng thêm đến khả năng đọc/export/open package, nhưng **không thay thế quy tắc identity cơ bản theo binary name và defining loader**. Hai module layer khác nhau có thể dùng loader khác nhau và tạo type identity khác nhau; song việc ở hai layer khác nhau không tự đủ chứng minh hai định danh kiểu khác nhau nếu lớp thực tế được chia sẻ/ủy quyền.

## 7. Các trường hợp riêng: array, primitive, bootstrap và hidden class

Quy tắc cặp tên và loader giải thích trực tiếp class/interface thông thường. Với các dạng đặc biệt, nên chú ý:

- **Array class** không có file bytecode riêng để `URLClassLoader.findClass` đọc như class thường; JVM tạo loại array tương ứng. Với array có phần tử là reference type, loader của array phản ánh loader định nghĩa thành phần tham chiếu đó. Hai `demo.plugin.ActionImpl[]` có component class từ hai defining loader khác nhau cũng là hai kiểu array khác nhau. `Class.getName()` của mảng dùng dạng `[Ldemo.plugin.ActionImpl;`.
- **Primitive type** như `int` và `boolean` có đối tượng `Class` đặc biệt, không được custom loader tự định nghĩa. `int.class.getClassLoader()` trả `null`; `int[].class.getName()` là `[I`.
- **Bootstrap loader** được JVM xử lý đặc biệt và `Class.getClassLoader()` thường trả `null`, ví dụ với `String.class`. Không suy rằng `null` là “không có loader”, cũng không so sánh chuỗi `"bootstrap"` với một object `ClassLoader`.
- **Hidden class** (API `MethodHandles.Lookup.defineHiddenClass`) không phải loại class có thể tra cứu thông thường qua `Class.forName` chỉ dựa trên tên. Tên được hiển thị bởi `getName()` có phần hậu tố đặc biệt. Không dùng hidden-class naming để thiết kế định danh plugin theo tên chuỗi.

Điểm chung vẫn là: khi đã có `Class<?>`, dùng identity của chính đối tượng `Class` để kiểm tra cùng kiểu; không giả lập logic so sánh bằng thao tác tự cắt chuỗi tên.

## 8. Chẩn đoán lỗi phát sinh từ nhiều class loader

Để điều tra sự cố, ghi **tên lớp, đối tượng defining loader, module và nguồn code** (nếu có) cho cả hai phía. Một hàm hỗ trợ:

~~~java
import java.security.CodeSource;

static void inspect(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    CodeSource source = type.getProtectionDomain() == null
            ? null
            : type.getProtectionDomain().getCodeSource();

    System.out.println("name=" + type.getName());
    System.out.println("loader=" + (loader == null ? "<bootstrap>" : loader));
    System.out.println("module=" + type.getModule());
    System.out.println("source=" + (source == null ? "<unknown>" : source.getLocation()));
}
~~~

Đây là **đoạn minh họa đặt trong một class**, không phải chương trình Java độc lập có `main()`. Kết quả `loader.toString()`/`module.toString()` có thể khác theo JDK và cách tạo loader; không dùng phần hiển thị đó làm khóa identity trong hệ thống. `CodeSource` có thể là `null` (hoặc không cung cấp location), nên không dựa tuyệt đối vào đường file.

| Hiện tượng | Nguyên nhân class loader đáng kiểm tra | Cách điều tra |
| --- | --- | --- |
| `ClassCastException` với hai tên class nhìn như nhau | Cùng binary name nhưng khác defining loader; hoặc quan hệ kiểu không đúng | In `getClass()` và `getClassLoader()` của object/target class; so `Class` bằng `==` |
| `ServiceConfigurationError: ... not a subtype` | Provider và host có thể đã nạp hai bản interface SPI cùng binary name | Xem loader của interface host và interface provider; tách shared API ra parent |
| `NoClassDefFoundError` | Dependency không thể được tìm/nạp trong loader cần dùng; cũng có thể do lỗi khởi tạo trước đó | Kiểm tra cause, classpath/module path, parent delegation, mã lỗi trước đó |
| `ClassNotFoundException` khi `Class.forName` | Loader được yêu cầu không tìm thấy binary name theo cơ chế của nó | Kiểm tra tên `$`, URL/JAR của plugin và loader được truyền |
| `LinkageError` hoặc lỗi loader constraint | Các chữ ký/tương tác yêu cầu cùng runtime type nhưng các loader giải quyết ra type không tương thích | Kiểm tra type trong field/method signatures và loader của mỗi type |
| `IllegalAccessError` qua ranh giới package/module | Runtime package khác nhau hoặc vi phạm accessibility/export | Kiểm tra defining loader, module graph, exports/opens |
| Class/plugin cũ không được unload sau reload | Còn tham chiếu mạnh đến loader, class, instance, thread, listener hoặc `ThreadLocal` | Tắt job/listener, xóa registry/cache, kiểm tra heap dump và TCCL |

Lỗi chỉ xuất hiện khi deploy hoặc hot reload thường gắn với **sự khác biệt trong classpath, class loader hierarchy hoặc trạng thái đã nạp lớp** so với môi trường build/test. Đừng vội sửa bằng ép kiểu hoặc reflection trước khi xác định chính xác loader định nghĩa mỗi phía.

### Context ClassLoader có phải defining loader không?

Không nhất thiết. `Thread.currentThread().getContextClassLoader()` là một context hữu ích để framework tìm plugin hoặc service tùy vào API, nhưng nó **không tự quyết định** loader sẽ thực sự định nghĩa class nào. Một lời gọi dùng context loader vẫn có thể delegate về parent. Nếu tạm thay Thread Context ClassLoader để tìm provider, phải khôi phục giá trị cũ trong `finally`, đặc biệt với thread pool.

## 9. Checklist thiết kế và kiểm thử

Khi xây một cơ chế nạp plugin an toàn với type identity, hãy xác minh:

1. **Tên đầu vào là binary name đúng**, đặc biệt với nested class: `Outer$Inner`, không dùng canonical name nếu API yêu cầu binary name.
2. **Defining loader được xác nhận** qua `Class.getClassLoader()` của kết quả, không suy luận từ loader truyền vào `loadClass`.
3. **Parent delegation và đường dẫn plugin rõ ràng**: kiểm tra implementation class không vô tình lọt vào parent classpath nếu mục tiêu là cô lập.
4. **Shared API chỉ có một identity** ở nơi host/plugin đều tham chiếu. Dùng `Action.class.isAssignableFrom(pluginClass)` hoặc `Action.class.isInstance(instance)` để kiểm tra trước khi ép.
5. **Kiểm thử class trùng tên ở hai loader**: so sánh `getName()`, `Class ==`, `getClassLoader()`, `isInstance()` và cast qua interface chung.
6. **Kiểm thử trường hợp ủy quyền về parent**: tạo hai loader khác nhau nhưng class thực tế do cha định nghĩa; xác nhận kết quả `Class` bằng nhau.
7. **Không dùng mỗi chuỗi tên làm ID runtime** trong registry hỗ trợ nhiều loader hoặc nhiều phiên bản plugin.
8. **Quy định lifecycle và unload**: ngừng nhận request, drain công việc cũ, giải phóng callback và những nơi lưu tham chiếu, đóng `URLClassLoader` để giải phóng tài nguyên mở. `close()` **không cưỡng ép GC/unload class** và không làm đối tượng đã tạo lập tức biến mất; JVM chỉ có thể thu hồi khi các điều kiện về khả năng truy cập/tham chiếu phù hợp.
9. **Dùng chung type một cách có chủ đích**: những gì phải đi qua ranh giới extension (interfaces, DTO, exceptions công khai) được nạp từ cùng không gian API; dependency implementation có thể cô lập.

## 10. Tự kiểm tra kiến thức

**Tình huống A:** hai URLClassLoader khác nhau cùng gọi `loadClass("demo.api.Action")`, cả hai delegate về parent. Có phải hai kiểu không?

Không. Nếu kết quả đều được parent định nghĩa, `a == b` là `true` dù loader khởi xướng khác nhau.

**Tình huống B:** hai URLClassLoader tự đọc đúng cùng file `demo/plugin/ActionImpl.class`, không delegate cho parent lớp implementation. Có thể ép trực tiếp instance của A sang `ActionImpl` của B không?

Không. Cùng binary name và bytecode, nhưng defining loader khác nên runtime type khác. Có thể dùng interface chung nếu interface đó có cùng type identity giữa các bên.

**Tình huống C:** hai class đều có `package demo.internal;` nhưng do các loader khác nhau định nghĩa. Chúng có tự nhiên được dùng thành viên package-private của nhau không?

Không. Runtime package còn phụ thuộc defining loader, không chỉ chuỗi tên package.

**Tình huống D:** gọi `Class.forName(name, false, child)` rồi thấy `result.getClassLoader() == parent`. Có phải JVM chọn sai loader không?

Không. Child là initiating loader; parent đã định nghĩa lớp theo quy tắc delegation.

## Tài liệu chuẩn

- [JVMS 17, `5.3 – Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): định danh class/interface theo binary name và defining loader; initiating loader, constraints và runtime package.
- [ClassLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, mô hình delegation.
- [Class – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()`, `getClassLoader()`, `isInstance()`, `isAssignableFrom()` và `cast()`.
- [URLClassLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nạp bytecode từ URL và giải phóng tài nguyên khi đóng.
