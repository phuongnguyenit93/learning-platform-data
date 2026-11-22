# Định danh lớp bằng tên nhị phân và defining loader

> **Chủ đề:** Java Core → ClassLoader → Định danh kiểu. Trong JVM, tên lớp chỉ là **một nửa** định danh kiểu runtime: đối với lớp/interface thông thường, JVM phân biệt bằng cặp **(binary name, defining class loader)**. Đây là cơ sở để hiểu tại sao cùng tệp `.class` nhưng nạp qua hai loader có thể sinh hai kiểu không tương thích.

## 1. Vì sao tên lớp giống nhau vẫn có thể là hai kiểu khác nhau?

Giả sử cả hai plugin đều chứa tệp `demo/Token.class` được biên dịch từ cùng một Java source:

```java
package demo;
public class Token {
    public String value() { return "ok"; }
}
```

Bạn có hai `Class<?>`, gọi là `a` và `b`, cùng trả về `"demo.Token"` khi gọi `getName()`. Chỉ thông tin đó **chưa đủ để khẳng định `a == b`**.

Theo JVM Specification `5.3`, sau khi được tạo, một lớp hoặc interface (không phải array) được xác định bởi:

```text
Runtime type identity = (binary name, defining class loader)

("demo.Token", loader A) != ("demo.Token", loader B)
("demo.Token", loader A) == ("demo.Token", loader A)
```

Hai dòng ký hiệu trên thể hiện quy tắc **định danh của kiểu**, không phải biểu thức Java chạy độc lập. Khi các loader khác nhau **thật sự định nghĩa** cùng binary name, JVM tạo ra hai kiểu runtime khác nhau, dù bytes của `.class` có thể giống hệt, đường dẫn JAR giống nhau và Java source giống nhau.

Vì vậy:

- `a.getName().equals(b.getName())` có thể là `true`.
- `a == b`, `a.equals(b)` có thể là `false` (với `Class`, `equals` dùng identity object).
- Object tạo từ `a` thường không được `b.cast(object)` chấp nhận.
- `a.getClassLoader()` và `b.getClassLoader()` cho biết **defining loader** của từng kiểu, không đơn thuần “loader từng được gọi để tìm class”.

Đây không phải lỗi do hai class khác package. **Ngay cả package và binary name đều giống nhau**, defining loader khác vẫn tạo khác biệt kiểu runtime.

## 2. Binary name: thành phần tên trong cặp định danh

*Binary name* là tên JVM dùng để định danh lớp/interface bình thường theo quy tắc JLS `13.1`:

| Khai báo Java | Binary name | Ghi chú |
| --- | --- | --- |
| `package demo; class Token {}` | `demo.Token` | Top-level class. |
| `package demo; class Outer { static class Inner {} }` | `demo.Outer$Inner` | Member class dùng `$`. |
| `java.util.Map.Entry` | `java.util.Map$Entry` | Trong source là tên kiểu member, còn tên nhị phân chứa `$`. |
| Local/anonymous class | Thường có `$` và chữ số do compiler tạo | Không hardcode số thứ tự do compiler sinh. |

Phân biệt ba dạng tên:

```text
Canonical Java name: demo.Outer.Inner
Binary name:         demo.Outer$Inner
JVM internal name:   demo/Outer$Inner
```

`Class.getName()` trả binary name cho **non-array, non-hidden reference class/interface bình thường**. `Class.forName("demo.Outer$Inner")` hoặc `loader.loadClass("demo.Outer$Inner")` tìm lớp member bằng binary name; chuỗi canonical `"demo.Outer.Inner"` không thay cho binary name trong trường hợp đó.

**Giới hạn:** mảng, primitive/void và hidden classes có biểu diễn/semantics riêng ở API `Class`. Bài này tập trung vào định danh lớp/interface thông thường; phần 8 giải thích mảng và primitive để tránh suy rộng sai.

## 3. Defining loader khác initiating loader

Khi JVM cần tạo kiểu mang tên `N`, nó có thể yêu cầu một loader `L1` đi tìm class. Loader này có thể:

1. **Tự định nghĩa:** đọc/generate bytes và gọi `defineClass(...)`. Khi đó `L1` là *defining loader* của class mới.
2. **Ủy quyền:** gọi loader khác `L2` nạp tên `N`. Nếu `L2` là bên thực sự gọi `defineClass`, thì `L2` là *defining loader*, trong khi `L1` chỉ khởi phát việc nạp qua delegation.

JVMS dùng thuật ngữ:

- **Defining loader:** loader **trực tiếp định nghĩa** class/interface từ binary representation.
- **Initiating loader:** loader mà JVM ghi nhận đã **khởi phát** quá trình nạp lớp tương ứng, có thể trực tiếp hoặc thông qua delegation.

Ví dụ delegation:

```text
Application requests "demo.Token" through pluginChild
                         |
                         v
               pluginChild.loadClass(...)
                         |
                         | parent delegation
                         v
                sharedParent.loadClass(...)
                         |
                         | reads Token.class + defineClass(...)
                         v
                   Class<demo.Token>
                   defining loader = sharedParent

pluginChild: initiating loader (may return Class defined by parent)
sharedParent: defining loader (also initiating loader)
```

Trong phạm vi mô hình JVM, các loader tham gia ở giữa chuỗi delegation **không nhất thiết đều được ghi nhận là initiating loader**; không coi việc “được gọi `loadClass`” là đồng nghĩa 100% với việc JVM đánh dấu nó là initiating loader. Cần nhìn vào kết quả runtime và quy tắc ở JVMS `5.3`.

Đối với một instance `Class<?> c`:

```java
ClassLoader definingLoader = c.getClassLoader();
```

`getClassLoader()` trả loader **định nghĩa** lớp, hoặc `null` cho lớp do bootstrap loader định nghĩa. Nó không trả một “loader theo yêu cầu gần nhất”. Nếu hỏi hai child loaders rồi cả hai delegate tới một parent chung, có thể thu về **chính cùng một `Class<?>`**, vì defining loader không đổi.

### Quan hệ parent không quyết định type identity trực tiếp

`loader.getParent()` cho biết parent trong cây delegation thông thường; **parent loader và defining loader không phải hai từ đồng nghĩa**. Chỉ khi một loader thực sự định nghĩa lớp, identity mới mang loader ấy. Parent-first là chiến lược phổ biến của `ClassLoader.loadClass` mặc định và `URLClassLoader`, nhưng custom class loaders có thể tổ chức delegation khác với mục đích rõ ràng.

## 4. Chứng minh bằng Java 17+: hai URLClassLoader nạp cùng bytes

Thí nghiệm đặt plugin class trong một thư mục **không có trên classpath của ứng dụng khởi động**, rồi tạo hai loader độc lập đọc cùng thư mục đó. Để ví dụ rõ ràng, hai loader dùng platform loader làm parent; plugin chỉ cần các API Java tiêu chuẩn.

Tạo cấu trúc:

```text
plugin-src/demo/Token.java
app-src/IdentityDemo.java
plugin-classes/    (được javac tạo)
app-classes/       (được javac tạo)
```

**File `plugin-src/demo/Token.java`:**

```java
package demo;

public class Token {
    public String value() {
        return "ok";
    }
}
```

**File `app-src/IdentityDemo.java`:**

```java
import java.lang.reflect.Array;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL[] urls = {
                Path.of("plugin-classes").toAbsolutePath().toUri().toURL()
        };
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(urls, platform);
             URLClassLoader second = new URLClassLoader(urls, platform);
             URLClassLoader delegated = new URLClassLoader(new URL[0], first)) {

            Class<?> a = Class.forName("demo.Token", false, first);
            Class<?> b = Class.forName("demo.Token", false, second);
            Class<?> c = Class.forName("demo.Token", false, delegated);

            Object value = a.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class: " + (a == b));
            System.out.println("distinct defining loaders: "
                    + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("same loader returns same Class: "
                    + (a == Class.forName("demo.Token", false, first)));
            System.out.println("first accepts object: " + a.isInstance(value));
            System.out.println("second accepts object: " + b.isInstance(value));
            System.out.println("delegation returns first Class: " + (c == a));
            System.out.println("delegated is defining loader: "
                    + (c.getClassLoader() == delegated));
            System.out.println("array classes identical: "
                    + (Array.newInstance(a, 0).getClass()
                    == Array.newInstance(b, 0).getClass()));
            System.out.println("array loader first: "
                    + (Array.newInstance(a, 0).getClass().getClassLoader()
                    == first));

            try {
                b.cast(value);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast: ClassCastException");
            }
        }
    }
}
```

Biên dịch từ **thư mục cha** chứa hai thư mục source:

```bash
javac -d plugin-classes plugin-src/demo/Token.java
javac -d app-classes app-src/IdentityDemo.java
java -cp app-classes IdentityDemo
```

Stdout đã kiểm chứng trên OpenJDK 21:

```text
same binary name: true
same Class: false
distinct defining loaders: true
same loader returns same Class: true
first accepts object: true
second accepts object: false
delegation returns first Class: true
delegated is defining loader: false
array classes identical: false
array loader first: true
cross-loader cast: ClassCastException
```

### Giải thích từng kết quả

1. `first` và `second` nhận **cùng `URL[]` và đọc cùng bytes**; nhưng chúng là **hai object loader khác nhau**. Cả hai đều tự định nghĩa `demo.Token`, tạo hai kiểu runtime khác nhau.
2. `getName()` chỉ kiểm tra **binary name** nên `true`; `a == b` là `false` vì defining loader khác.
3. Gọi lại `Class.forName("demo.Token", false, first)` trả về cùng `Class<?> a`. Một loader vận hành đúng không tạo một định nghĩa thứ hai với cùng binary name của nó.
4. `a.isInstance(value)` là `true` nhưng `b.isInstance(value)` là `false`; `Class.cast` của `b` ném `ClassCastException`. **Object từ một định nghĩa không tự động là instance của định nghĩa cùng tên ở loader khác**.
5. `delegated` có mảng URL rỗng và parent là `first`. Khi tìm `demo.Token`, nó delegate tới `first` và nhận đúng `a`. Vì vậy `c == a` là `true` nhưng `c.getClassLoader() == delegated` là `false`: **initiating không buộc là defining**.
6. Hai `demo.Token[]` cũng khác nhau; array class có identity gắn với **kiểu phần tử**. `Array.newInstance(a, 0)` tạo mảng có defining loader được phản ánh bằng `first`.
7. `URLClassLoader` triển khai `AutoCloseable` nên có thể đóng bằng try-with-resources. `close()` đóng tài nguyên mà loader mở; nó **không buộc JVM unload ngay** những class đã được định nghĩa.

Lưu ý thí nghiệm chỉ nạp plugin qua URLClassLoader ở `plugin-classes`; không thêm `plugin-classes` vào `-cp`. Nếu class được parent nhìn thấy trước, parent-first delegation có thể trả lớp do parent định nghĩa và làm thí nghiệm không còn minh họa hai defining loaders khác nhau.

## 5. Hệ quả thực tế: vì sao cast và instanceof thất bại?

Phép ép kiểu kiểm tra **quan hệ giữa các runtime type**, không kiểm tra chuỗi tên class. Trong thí nghiệm trước, `a.isInstance(value)` là `true`, còn `b.isInstance(value)` là `false` và `b.cast(value)` ném `ClassCastException`: `a` và `b` đều mang tên `demo.Token` nhưng do hai loader định nghĩa.

Ở ứng dụng plugin, lỗi tương tự xảy ra khi host và plugin cùng đóng gói, **tự định nghĩa** hai bản `api.Plugin`. Dù source plugin ghi `implements api.Plugin`, object chỉ implement bản interface mà loader của nó đã liên kết. Cần cho hai phía dùng chung **cùng `Class<?>` của hợp đồng API** từ một loader được chia sẻ, hoặc chuyển dữ liệu qua giao thức trung lập nếu chủ ý cách ly. Bài về `ClassCastException` phân tích stack trace và quy trình khắc phục cụ thể.

## 6. Runtime package và quyền truy cập cũng phụ thuộc defining loader

Runtime package được xác định bằng **(tên package, defining loader)**. Hai class đều khai báo `package com.acme;` nhưng được các loader A và B định nghĩa nằm trong **hai runtime package** khác nhau. Vì thế package-private không tự cho phép truy cập chéo; khi JVM kiểm tra một symbolic reference, truy cập sai có thể dẫn đến `IllegalAccessError`.

`protected`, nestmates và JPMS còn có quy tắc truy cập riêng. `exports`/`opens` của module không thay thế điều kiện cùng runtime package. Các bài về runtime package và package-private triển khai thí nghiệm truy cập chi tiết.

## 7. Defining loader và initiating loader ảnh hưởng linkage ra sao?

JVM dùng **loading constraints** để giữ an toàn kiểu khi liên kết field, method, override hoặc interface xuyên qua các loader. Chẳng hạn hai phía cùng sử dụng tên `com.acme.Message` trong method descriptor, nhưng loader của mỗi bên ánh xạ tên đó tới `Class<?>` khác nhau, có thể vi phạm constraint và gây `LinkageError`.

Phân biệt ba trường hợp: hai định nghĩa cùng tên **có thể cùng tồn tại** khi chưa cần thống nhất; **cast sai** thường báo `ClassCastException`; **linking cần cùng kiểu nhưng bất nhất** có thể báo loading constraint violation. Bài về loading constraints đi sâu điều kiện áp đặt và thời điểm kiểm tra.

## 8. Các trường hợp đặc biệt: array, primitive và bootstrap

Với **array**, JVM tạo lớp mảng khi cần. `getClassLoader()` của mảng phần tử reference phản ánh defining loader của kiểu phần tử cơ sở; mảng primitive có loader `null`. Vì vậy hai lớp `demo.Token` khác identity tạo ra hai kiểu `demo.Token[]` khác identity, dù tên mảng giống nhau.

Các `Class<?>` của primitive và `void` (`int.class`, `void.class`) do JVM cung cấp theo cơ chế riêng; không thể dùng `loadClass("int")` để nạp chúng từ class file. Array descriptors, hidden classes và các kiểu đặc biệt cần áp dụng quy tắc tương ứng, không suy diễn cứng từ cặp binary name + defining loader của class/interface thông thường.

## 9. Những sai lầm khi debug và cách tự kiểm chứng

### Sai lầm 1: Chỉ log getName() là đủ

Hai `Class<?>` có thể có cùng `getName()` nhưng khác defining loader. Hãy log **cả hai thông tin** và kiểm tra identity thực tế:

```java
// Đặt trong method nhận hai biến Class<?> left, right:
System.out.println("left name = " + left.getName());
System.out.println("right name = " + right.getName());
System.out.println("same class object = " + (left == right));
System.out.println("left defining loader = " + left.getClassLoader());
System.out.println("right defining loader = " + right.getClassLoader());
```

Đây là snippet minh họa; `left` và `right` cần đến từ code gọi. `ClassLoader.toString()` chỉ hỗ trợ debug, **không phải định danh bền vững** để lưu trong database. `System.identityHashCode(loader)` cũng chỉ cho một hash phục vụ quan sát; có thể trùng giữa hai object khác nhau nên không thay thế phép so sánh `==`.

### Sai lầm 2: Nghĩ hai URLClassLoader trỏ cùng JAR thì class giống nhau

Hai loader khác nhau cùng `URL` vẫn có thể định nghĩa hai class riêng. Chỉ khi **cả hai yêu cầu được delegate tới cùng defining loader** mới nhận lại cùng class identity. Đường dẫn file, checksum bytecode, package và `Class.getName()` không tự quyết định identity.

### Sai lầm 3: Dùng Class.forName mà không chủ động chọn loader

`Class.forName(String)` dùng quy tắc loader của caller; `Class.forName(String, boolean, ClassLoader)` cho phép truyền loader cụ thể. Trong plugin/container, chọn sai loader dễ gây `ClassNotFoundException` hoặc tạo/nhận nhầm kiểu có cùng tên.

`Thread.currentThread().getContextClassLoader()` (TCCL) là một cơ chế loader khác, hữu ích cho SPI/framework, nhưng **không có nghĩa** nó luôn là defining loader của một class. Muốn biết class do ai định nghĩa, dùng `clazz.getClassLoader()`.

### Sai lầm 4: Cố cast “cùng interface source” giữa hai loader

Nếu host và plugin có hai bản class của cùng API, sửa cấu hình classpath một cách ngẫu nhiên không bảo đảm hợp nhất identity. Nên bố trí **API chung ở loader chia sẻ**, tránh đưa bản copy API vào private/plugin namespace và kiểm tra parent delegation.

### Sai lầm 5: Nghĩ đóng loader là class lập tức biến mất

Đóng `URLClassLoader` không reset các `Class<?>` hay object đã được tạo. Thread context loader, cache, static field, thread hoặc hook có thể giữ strong reference làm loader chưa thể được thu hồi.

## 10. Quy trình giải quyết xung đột loader trong dự án thật

1. **Xác định hai kiểu đang tranh chấp.** Từ `ClassCastException`, `LinkageError` hoặc thông tin plugin/container, lấy hai `Class<?>` nếu có thể và so sánh `getName()`, `==`, `getClassLoader()`.
2. **Tìm nguồn định nghĩa**: đường dẫn JAR/module, dependency graph, đường nạp resource; kiểm tra liệu host và plugin có bundle trùng API. `clazz.getProtectionDomain().getCodeSource()` có thể hỗ trợ nhưng cũng có thể `null` và không quyết định class identity.
3. **Vẽ delegation topology thực tế:** ai gọi `loadClass`, parent là ai, chính sách parent-first/child-first của từng loader, class nào do loader nào thực sự `defineClass`.
4. **Xác định kiểu cần chia sẻ** giữa các ranh giới: interface, DTO, exception và return/parameter types trong phương thức. Chỉ định một định nghĩa dùng chung với một loader chung.
5. **Đảm bảo bytecode/dependency nhất quán:** nâng cấp các phiên bản API, không âm thầm tạo duplicate copies, kiểm tra module readability/exports/opens khi dùng JPMS.
6. **Tái tạo bằng ví dụ nhỏ** như `IdentityDemo` để chứng minh chính xác cặp (name, loader) nào đang khác nhau. Đừng đoán qua tên lớp in ra trong message của lỗi.
7. **Kiểm tra lại bằng object identity và type check**, sau đó xem xét class lifecycle/unloading nếu có reload/hot deploy.

Với HotSpot, log tải lớp có thể hỗ trợ:

```bash
java -Xlog:class+load=info -cp app-classes IdentityDemo
```

Các dòng log class loading cho biết quá trình nạp và nguồn class theo mức logging hiện tại; đây là dữ liệu bổ trợ, không thay thế việc so sánh `Class<?>` và defining loader trong app. Quyền quan sát khác nhau giữa JVM/version.

## 11. Tự kiểm tra

1. **Hai `Class<?>` trả cùng `"com.acme.Plugin"` từ `getName()` có bắt buộc bằng nhau không?** Không. Chúng chỉ cùng binary name; defining loader có thể khác.
2. **Một child loader gọi `parent.loadClass("demo.Token")` rồi trả đúng object `Class<?>` của parent. Defining loader là ai?** Parent (nếu parent trực tiếp định nghĩa class). Child có thể là initiating loader nhưng không phải defining loader.
3. **Hai child loaders cùng delegate một class tới parent chung thì có thể trả cùng class không?** Có, nếu cùng trả class đã được parent định nghĩa.
4. **Hai loader đọc cùng byte-for-byte `Token.class` nhưng mỗi loader tự `defineClass` thì `a == b` là gì?** `false`.
5. **Tại sao `Class.cast` ném `ClassCastException` dù hai tên giống hệt?** Bởi vì kiểm tra kiểu sử dụng identity runtime; binary name trùng chưa đủ.
6. **Hai lớp cùng `package com.acme;` từ hai defining loaders có cùng runtime package không?** Không; runtime package được phân biệt bởi tên package và defining loader.
7. **`Class.getClassLoader() == null` với `String.class` có nghĩa chưa load không?** Không; đó là bootstrap loader.
8. **Hai lớp cùng tên có nhất thiết gây `LinkageError` ngay lập tức không?** Không; chúng có thể cùng tồn tại ở loader khác nhau. Loading constraint vi phạm, lặp define cùng loader hoặc hành động sử dụng không hợp lệ mới gây lỗi tùy trường hợp.
9. **Hai mảng có kiểu phần tử do hai loader định nghĩa khác nhau có cùng kiểu không?** Không; JVM gắn array identity với component type và loader tương ứng.

## 12. Tài liệu chuẩn

- [JVMS `5.3` — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): phân biệt defining/initiating loader và định danh runtime bằng cặp (binary name, defining loader).
- [JVMS `5.3.3` — Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.3): array class do JVM tạo và dùng defining loader của component type.
- [JVMS `5.3.4` — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): duy trì an toàn kiểu khi liên kết qua nhiều loader.
- [JLS `13.1` — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.1): quy tắc binary names.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `defineClass`, delegation, defining loader và array class.
- [Java SE 21 `Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isInstance` và `cast`.
- [Java SE 21 `URLClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): URL-based loading, parent delegation và `close`.
