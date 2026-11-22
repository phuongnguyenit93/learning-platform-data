# Truy cập package-private giữa các lớp do ClassLoader khác nhau định nghĩa

## 1. Tình huống và câu trả lời cốt lõi

Giả sử hai lớp Java cùng khai báo `package lab.boundary;`. Khi biên dịch chung, lớp này có thể gọi phương thức **package-private** (không có `public`, `protected` hoặc `private`) của lớp kia. Nhưng nếu tại runtime hai lớp được **định nghĩa bởi hai ClassLoader khác nhau**, quyền truy cập package-private đó **không còn hợp lệ**, dù chuỗi tên package giống hệt nhau.

Điều kiện then chốt không phải chỉ là *tên package trong source* mà là **run-time package**. Theo JVM Specification, run-time package của một class/interface được xác định bởi:

1. **Tên package** (package name).
2. **ClassLoader đã định nghĩa lớp** (defining loader).

Vì vậy:

~~~text
Compile time:
  Host.java  -> package lab.boundary
  Guest.java -> package lab.boundary
  => javac cho phép Guest gọi Host.secret() (package-private)

Runtime:
  Host  -> package lab.boundary, defining loader = L_parent
  Guest -> package lab.boundary, defining loader = L_child

  Tên package giống nhau                  : ĐÚNG
  Định danh run-time package giống nhau    : SAI
  Guest gọi Host.secret() (package-private): IllegalAccessError
~~~

Đây là **quy tắc truy cập ở mức JVM**, không phải lỗi do trình biên dịch tự ý đổi luật. ClassLoader tạo nên một phần ranh giới định danh kiểu và ranh giới package lúc chạy.

**Sau bài này, bạn cần:**

- Phân biệt *package trong source* với *run-time package* của JVM.
- Giải thích tại sao tên package giống nhau nhưng defining loader khác nhau có thể gây `IllegalAccessError`.
- Đọc được bằng chứng `getPackageName()` và `getClassLoader()` trong chương trình chạy độc lập Java 17+.
- Phân biệt lỗi kiểm tra quyền truy cập khi **biên dịch**, khi **link/resolution** và khi dùng **reflection**.
- Biết các cách thiết kế API giữa host và plugin khi mỗi bên có loader riêng.

## 2. Package-private có nghĩa gì ở từng thời điểm?

### 2.1. Trong mã nguồn và khi biên dịch

Một thành viên không khai báo modifier truy cập có **package access**, thường gọi là *package-private* hoặc *default access*:

~~~java
package lab.boundary;

public class Host {
    static String secret() { return "parent-only"; } // package-private
    public static String open() { return "public-ok"; } // public
}
~~~

Một lớp khác trong cùng package nguồn có thể gọi `Host.secret()` nếu các yêu cầu khác đều hợp lệ:

~~~java
package lab.boundary;

public class Guest {
    public static String callPrivate() {
        return Host.secret();
    }
}
~~~

Hai đoạn trên là **hai tệp Java minh họa riêng**, không phải một tệp độc lập. Nếu `Guest.java` biên dịch với `Host.class` trên compile classpath, `javac` thấy cả hai nằm trong `lab.boundary` và cho phép lời gọi. Tuy nhiên, compiler **không biết chắc** hai lớp sẽ được loader nào định nghĩa trong mọi lần chạy tương lai.

Nếu đổi package của `Guest` thành `other.pkg` mà vẫn gọi `Host.secret()`, `javac` sẽ báo lỗi truy cập ngay ở compile time. Đó là tình huống **khác** với bài học: ở đây source code **biên dịch được**, nhưng runtime loading làm thay đổi ranh giới package.

### 2.2. Trong JVM: cùng chuỗi tên chưa đủ

JVM Specification `5.3` định nghĩa một lớp runtime bằng **binary name + defining loader**, và run-time package bằng **package name + defining loader**.

Ký hiệu:

~~~text
Host:
  binary name     = lab.boundary.Host
  package name    = lab.boundary
  defining loader = L_parent
  run-time package = (lab.boundary, L_parent)

Guest:
  binary name     = lab.boundary.Guest
  package name    = lab.boundary
  defining loader = L_child
  run-time package = (lab.boundary, L_child)
~~~

Nếu `L_parent != L_child` thì hai run-time packages **khác nhau**. Truy cập package-private giữa hai lớp không được phép chỉ vì `getPackageName()` trả cùng chuỗi.

Điều này cũng giải thích một vấn đề quen thuộc trong plugin/container: loader riêng bảo đảm cô lập kiểu, nhưng việc cô lập có thể làm hỏng các lời gọi package-private vốn được compiler cho phép khi các source nằm trong cùng một package.

### 2.3. Defining loader và initiating loader không giống nhau

- **Defining loader** là loader thực sự **định nghĩa** class, trực tiếp hoặc qua cơ chế JVM tương ứng. `SomeClass.class.getClassLoader()` phản ánh defining loader (có thể là `null` với bootstrap-defined class).
- **Initiating loader** là loader **khởi xướng việc tra cứu** class, có thể ủy quyền việc định nghĩa cho parent.

Ví dụ: `L_child.loadClass("lab.boundary.Host")` có thể trả về `Host` được **`L_parent` định nghĩa** vì ủy quyền parent-first. Khi xét run-time package, dùng **defining loader** của mỗi lớp, không kết luận dựa trên việc “child từng yêu cầu load”.

Trong ví dụ thực hành bên dưới, parent định nghĩa `Host` còn child định nghĩa `Guest`. Mặc dù child có thể tìm `Host` qua parent, chúng vẫn nằm ở hai run-time packages khác nhau.

## 3. JVM phát hiện vi phạm quyền truy cập như thế nào?

### 3.1. Kiểm tra khi resolving symbolic reference

Trong bytecode của `Guest.callPrivate()`, lời gọi `Host.secret()` là tham chiếu đến một phương thức. Khi JVM **resolution** tham chiếu đó, nó kiểm tra phương thức đích có thể được truy cập từ lớp đang gọi không.

Quy tắc quan trọng trong [JVMS `5.4`.4](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4):

- `public` method: có thể truy cập nếu lớp chứa nó cũng truy cập được và đáp ứng các quy tắc có liên quan.
- `protected`: tuân theo quy tắc subclass/same run-time package và các điều kiện bổ sung.
- Không có modifier truy cập (*package-private*): cho phép nếu **lớp khai báo member** và **lớp đang truy cập** thuộc **cùng run-time package**.
- `private`: dựa trên lớp/nest hợp lệ, không phải chỉ chung package.

Khi truy cập method không hợp lệ tại resolution, JVM ném **`java.lang.IllegalAccessError`**. Lỗi này là một `LinkageError` (thuộc nhánh `Error`), **không phải** `IllegalAccessException` của reflection.

**Thời điểm quan sát:** JVM được phép resolve một số tham chiếu sớm hoặc muộn theo đặc tả. Trong ví dụ cụ thể, `IllegalAccessError` xuất hiện khi thực thi lời gọi `Guest.callPrivate()`. Không nên khẳng định mọi JVM luôn ném lỗi đúng ở một opcode nếu các tình huống linking phức tạp khác xảy ra.

### 3.2. Không phải lỗi “không tìm thấy lớp”

Hai lớp trong ví dụ có thể đều đã được load thành công. Tìm thấy `Host` và `Guest` không bảo đảm câu lệnh `Host.secret()` được phép thực thi. Cần phân biệt:

| Hiện tượng | Ý nghĩa |
|---|---|
| `ClassNotFoundException` | API yêu cầu tìm lớp theo tên nhưng loader không tìm được lớp |
| `NoClassDefFoundError` | JVM không có/không dùng được một định nghĩa lớp bắt buộc tại runtime; có nhiều nguyên nhân |
| `IllegalAccessError` | JVM tìm được định nghĩa nhưng **kiểm tra quyền truy cập** tại linking/resolution thất bại |
| `IllegalAccessException` | API reflection báo một truy cập bị từ chối; đây là checked exception thuộc cơ chế reflection |
| `InaccessibleObjectException` | Có thể gặp khi cố thay đổi kiểm tra quyền truy cập bằng deep reflection nhưng bị chặn, nhất là qua ranh giới module |
| `ClassCastException` | Ép kiểu runtime không hợp lệ; trong plugin có thể do hai class cùng tên nhưng khác defining loader |

Sự khác biệt giữa `IllegalAccessError` và `IllegalAccessException` đặc biệt hữu ích: một lỗi là kết quả **kiểm tra truy cập JVM của bytecode**, lỗi kia thường phát sinh từ thao tác **reflection**.

## 4. Sơ đồ ClassLoader của ví dụ

Bố cục có chủ đích:

~~~text
Application / System ClassLoader (parent)
  |
  +-- định nghĩa lab.boundary.Host
  +-- định nghĩa Launcher
  |
  v  (parent-first delegation)
URLClassLoader child
  |
  +-- không định nghĩa lại Host
  +-- định nghĩa lab.boundary.Guest từ build/guest

Guest -> Host.open()   : hợp lệ (public)
Guest -> Host.secret() : IllegalAccessError (package-private)
~~~

**Điểm quyết định:** `Guest.class` **không** nằm trên runtime classpath của parent; ngược lại `Host.class` **chỉ** nằm trong output dành cho parent. Nếu vô tình thêm cả `build/guest` vào system classpath, parent-first delegation có thể khiến **cả Host và Guest đều do parent định nghĩa**, dẫn đến bài thử không còn minh họa ranh giới loader như mong muốn.

Ví dụ dùng `URLClassLoader` tiêu chuẩn và một lớp `Launcher`. Không cần custom subclass hay thư viện ngoài.

## 5. Thực hành Java 17+: ví dụ độc lập kiểm chứng lỗi

### 5.1. Tạo cây thư mục

Từ một thư mục trống tên tùy chọn (ở đây gọi là `demo`), tạo cây source như sau:

~~~text
demo/
  src-host/
    lab/
      boundary/
        Host.java
  src-guest/
    lab/
      boundary/
        Guest.java
  src-launcher/
    Launcher.java
  build/
    host/              # output của Host và Launcher
    guest/             # output của Guest
~~~

Có thể tạo các thư mục `src-*` và `build/*` bằng IDE/file explorer hoặc command line trước khi biên dịch. Hai đầu ra phải **riêng biệt**: chương trình sẽ chạy với system classpath **chỉ** gồm `build/host`.

### 5.2. Tệp `src-host/lab/boundary/Host.java`

~~~java
package lab.boundary;

public class Host {
    static String secret() {
        return "parent-only";
    }

    public static String open() {
        return "public-ok";
    }
}
~~~

`Host` là **public class** nên guest ở run-time package khác có thể tham chiếu chính class này. Nhưng `secret()` không có modifier: nó chỉ cho phép code thuộc cùng **run-time package** gọi. `open()` public được dùng làm phép thử đối chứng.

### 5.3. Tệp `src-guest/lab/boundary/Guest.java`

~~~java
package lab.boundary;

public class Guest {
    public static String callPrivate() {
        return Host.secret();
    }

    public static String callPublic() {
        return Host.open();
    }
}
~~~

Ở compile time, `javac` nhận hai class cùng source package `lab.boundary` nên cho phép cả hai lời gọi. Tình huống vi phạm chỉ phát sinh sau khi `Guest` được loader khác định nghĩa tại runtime.

### 5.4. Tệp `src-launcher/Launcher.java`

~~~java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import lab.boundary.Host;

public class Launcher {
    public static void main(String[] args) throws Exception {
        URL source = Path.of("build/guest").toUri().toURL();

        try (URLClassLoader child = new URLClassLoader(
                new URL[] { source },
                Host.class.getClassLoader())) {

            Class<?> guest = Class.forName(
                    "lab.boundary.Guest", true, child);

            System.out.println("samePackageName="
                    + Host.class.getPackageName()
                            .equals(guest.getPackageName()));

            System.out.println("sameLoader="
                    + (Host.class.getClassLoader()
                            == guest.getClassLoader()));

            System.out.println("public="
                    + guest.getMethod("callPublic").invoke(null));

            try {
                guest.getMethod("callPrivate").invoke(null);
            } catch (InvocationTargetException ex) {
                System.out.println("failure="
                        + ex.getCause().getClass().getSimpleName());
            }
        }
    }
}
~~~

**Giải thích cấu trúc:**

1. `Path.of("build/guest").toUri().toURL()` đưa directory chứa `Guest.class` vào nguồn tìm kiếm của `URLClassLoader`.
2. Parent là `Host.class.getClassLoader()`: trong cách chạy này, đó là system/application loader, vốn đã định nghĩa `Host`.
3. Parent-first delegation tìm `lab.boundary.Guest` ở parent trước; vì parent không có `Guest.class`, loader con mới tìm trong `build/guest` và định nghĩa `Guest`.
4. `Class.forName(..., true, child)` tìm và khởi tạo `Guest`. `Guest` có public methods; reflection ở đây chỉ dùng để gọi hai methods của một class mà `Launcher` không compile-time phụ thuộc.
5. `Guest.callPublic()` gọi được `Host.open()`: `Host` public, `open()` public; cả hai class thuộc các unnamed modules của loader tương ứng, ở đây vẫn đáp ứng quyền truy cập public.
6. `Guest.callPrivate()` gây `IllegalAccessError` khi liên kết lời gọi `Host.secret()`. Reflection bọc lỗi ném từ invoked method trong `InvocationTargetException`; code lấy `getCause()` và in tên lỗi gốc.

### 5.5. Biên dịch/chạy đúng

Từ thư mục `demo`, tạo hai thư mục output. Trên Bash:

~~~sh
mkdir -p build/host build/guest
javac --release 17 -d build/host src-host/lab/boundary/Host.java src-launcher/Launcher.java
javac --release 17 -cp build/host -d build/guest src-guest/lab/boundary/Guest.java
java -cp build/host Launcher
~~~

Trên Windows PowerShell, câu lệnh tương đương:

~~~powershell
New-Item -ItemType Directory -Force build/host, build/guest | Out-Null
javac --release 17 -d build/host src-host/lab/boundary/Host.java src-launcher/Launcher.java
javac --release 17 -cp build/host -d build/guest src-guest/lab/boundary/Guest.java
java -cp build/host Launcher
~~~

Điều kiện bắt buộc: **không thêm `build/guest` vào lệnh chạy `java -cp build/host Launcher`**. Giữ thư mục làm việc ở `demo` để đường dẫn `build/guest` trong `Launcher` trỏ đúng nơi.

**Stdout đã kiểm chứng với JDK 21 biên dịch mức `--release 17`:**

~~~text
samePackageName=true
sameLoader=false
public=public-ok
failure=IllegalAccessError
~~~

Kết quả có bốn tầng nghĩa:

- `samePackageName=true`: hai class khai báo đúng cùng chuỗi tên package.
- `sameLoader=false`: defining loader **khác nhau**, do đó run-time package khác nhau.
- `public=public-ok`: class vẫn tìm được và public method hợp lệ; không phải lỗi thiếu class hay path.
- `failure=IllegalAccessError`: lời gọi package-private bị từ chối bởi JVM; việc `javac` từng cho qua không bảo đảm runtime access.

Không cần in `URLClassLoader.toString()` vì chuỗi định danh loader phụ thuộc runtime. So sánh đối tượng loader bằng `==` có ý nghĩa đúng hơn.

### 5.6. Kiểm tra bytecode để biết lỗi nằm ở đâu

~~~sh
javap -classpath build/guest -c lab.boundary.Guest
~~~

Trong `callPrivate()`, `javap` hiển thị lệnh gọi `invokestatic` trỏ tới `lab/boundary/Host.secret`. Cú pháp bytecode đã được tạo thành công lúc biên dịch; lỗi xuất hiện khi JVM xử lý quyền truy cập đối với method reference ở runtime.

Một phép thử đối chứng: nếu đưa `Guest.class` lên **system classpath** cùng `Host.class` trước khi khởi chạy, parent-first loader có thể định nghĩa cả hai và phép gọi package-private có thể thành công. Khi đó hãy kiểm tra lại `sameLoader`: nếu bằng `true` thì thí nghiệm không còn tách hai run-time package. Đó là **một môi trường chạy khác**, không phải cách “sửa tắt” cho hệ plugin muốn cô lập loader.

## 6. Phân biệt compile-time package và run-time package

Trình biên dịch Java xem các khai báo `package lab.boundary;` và classpath tại lúc biên dịch để quyết định có cho phép gọi package-private hay không. Khi chạy, JVM liên kết symbolic reference và kiểm tra **runtime package = (tên package, defining loader)**; hai tên package bằng nhau vẫn có thể thuộc hai runtime package khác nhau.

Vì vậy trong thí nghiệm trên, source `Guest` biên dịch được nhưng lời gọi tới thành viên package-private của `Host` bị `IllegalAccessError` khi class do loader khác định nghĩa. Biên dịch thành công không bảo đảm access check runtime thành công.

## 7. Tại sao framework/plugin dễ gặp vấn đề này?

Các hệ thống plugin, application server và container đôi khi tạo ClassLoader cho từng plugin/ứng dụng. Chúng có thể:

- Chia sẻ một API ở parent loader.
- Nạp implementation plugin qua child loader.
- Có hai phiên bản dependency cùng package dưới các child loaders khác nhau.
- Load một số class từ parent, một số từ child, dù nguồn build ban đầu đặt chúng trong cùng package.

Ví dụ:

~~~text
Parent loader:
  api/Service.class
  shared/internal/Helper.class

Plugin loader A:
  shared/internal/PluginTask.class

Plugin loader B:
  shared/internal/AnotherTask.class
~~~

Nếu `PluginTask` trực tiếp gọi `Helper.packagePrivateMethod()` (giả sử package đều là `shared.internal`), lời gọi có thể compile thành công khi build đặt cả hai nguồn trong cùng package. Nhưng runtime `Helper` do parent định nghĩa, còn `PluginTask` do plugin loader A định nghĩa nên **khác run-time package**, dẫn tới lỗi truy cập khi resolution.

Với Plugin A và Plugin B, ngay cả hai class cùng tên trong hai loader riêng cũng là **hai runtime types khác nhau**, có thể gây thêm `ClassCastException` nếu dùng kiểu implementation làm API chung. Đây là vấn đề khác nhưng có chung căn nguyên: **defining loader là thành phần của định danh kiểu/package**.

## 8. Thiết kế sửa đúng nguyên nhân

### 8.1. Sử dụng hợp đồng public dành cho ranh giới loader

Khi **chủ đích** tách lớp bằng nhiều loader, cách bền vững là công khai một hợp đồng giao tiếp cần thiết:

~~~java
package lab.api;

public interface Service {
    String execute();
}
~~~

Đoạn trên minh họa **API contract**, không phải một chương trình runnable riêng. Đặt interface này ở classpath/JAR chung do parent loader định nghĩa, sau đó cho plugin định nghĩa implementation và giao tiếp thông qua `public` methods của interface.

Lợi ích:

- Code từ các loader khác nhau không cần gọi package-private của nhau.
- Host và plugin cùng tham chiếu **một Class object `lab.api.Service`** do parent loader định nghĩa, tránh bất đồng type identity.
- Implementation và dependency nội bộ của plugin vẫn có thể được cô lập.

Nếu bắt buộc cung cấp một hành vi, hãy cân nhắc `public` API nhỏ có kiểm soát, một adapter/bridge công khai, hoặc thay đổi cách phân chia lớp giữa parent/child. Đừng tùy tiện biến mọi internal method thành `public` chỉ để che giấu một lỗi classloader; quyền public là một phần contract cần cân nhắc.

### 8.2. Nếu cần package-private thật sự, đặt các class trong cùng run-time package

Nếu hai class **thực sự phải** chia sẻ package-private logic, chúng phải có cùng tên package **và** cùng defining loader ở runtime. Với ứng dụng dùng nhiều loader, điều này có thể yêu cầu gom chúng vào cùng phía của ranh giới loader hoặc thiết kế lại kiến trúc module/plugin.

Tuy nhiên, chỉ đổi parent loader hoặc thêm JAR vào classpath tùy tiện có thể tạo xung đột dependency, duplicate classes, hoặc phá isolation. Điều kiện thành công phải được kiểm chứng bằng `getClassLoader()` cho **cả hai lớp** sau khi triển khai.

### 8.3. Reflection và mở module không làm mất điều kiện run-time package

- `setAccessible(true)` ảnh hưởng đến **truy cập qua reflection** theo các quy tắc tương ứng; nó **không biến** một bytecode `invokestatic Host.secret()` thành lời gọi package-private hợp lệ qua hai run-time packages.
- Với **named modules**, `requires`, `exports`, `opens` còn điều chỉnh khả năng dùng public types và deep reflection. `exports` hoặc `opens` **không tự cấp** quyền package-private giữa hai defining loaders khác nhau.
- Đừng thay package-private bằng `protected` với giả định “loader khác nhưng subclass sẽ được tất cả quyền”: `protected` có các quy tắc subclass, receiver và runtime package riêng, cần phân tích đúng từng đường gọi.

## 9. Chẩn đoán lỗi trong dự án thực tế

Khi thấy `IllegalAccessError` trỏ tới method/field trông như “cùng package”:

1. **Đọc đúng caller và member đích.** Stack trace thường có tên class tham chiếu, tên member và, trên JVM hiện đại, có thể có thông tin loader/module.
2. **Xác định access modifier của member** trong bytecode đang chạy, không chỉ trong source đã sửa. Có thể dùng `javap -p` hoặc `javap -c -p`, rồi xác nhận đúng JAR/version.
3. **Kiểm tra defining loader của hai class** bằng `SomeClass.class.getClassLoader()` hoặc log/class-loading diagnostics. Chỉ so sánh chuỗi `getPackageName()` là chưa đủ.
4. **Xem parent delegation và classpath nguồn.** Nếu parent đã có cùng một class, child-first/parent-first policy và nguồn class thực tế ảnh hưởng class được định nghĩa ở đâu.
5. **Nếu ứng dụng dùng JPMS**, kiểm tra thêm `clazz.getModule()`, readability, exports/opens. Những quy tắc đó có thể cùng gây lỗi access nhưng là nguyên nhân khác với package-private split runtime packages.
6. **Thử ví dụ rút gọn.** Hai class cùng package, xuất ra hai thư mục, dùng system/child loader tách biệt, cho public call thành công rồi thử package-private call. Đây là cách chứng minh vấn đề access mà không phụ thuộc vào toàn bộ framework.

### Các câu hỏi loại trừ nhanh

| Dấu hiệu | Ưu tiên điều tra |
|---|---|
| `javac` báo `is not public ... cannot be accessed from outside package` | Package/access ngay trong source, chưa đến runtime |
| Runtime `IllegalAccessError` với package-private member | Defining loader và run-time package; sau đó xét version/modifiers |
| `IllegalAccessError` với `public` type trong named module | Module readability/`exports` |
| `IllegalAccessException` khi gọi `Method.invoke` | Quyền reflection, có thể cần `canAccess` hoặc API công khai |
| `ClassCastException` khi class names giống nhau | Hai Class objects cùng tên nhưng defining loaders khác nhau |
| `ClassNotFoundException` | Nguồn class/JAR, đường classpath, loader được truyền vào |
| `NoSuchMethodError` | ABI/version mismatch, dependency runtime khác compile time |

Không xử lý tất cả những lỗi này bằng cách thêm `--add-opens`, `--add-exports` hoặc `setAccessible(true)`. Hãy xác định nguyên nhân trước vì các cờ đó không làm thay đổi defining loader và run-time package của class.

## 10. Những nhầm lẫn phổ biến

1. **“Hai file đều có `package lab.boundary;` nên package-private luôn hoạt động.”** Sai tại runtime nếu defining loader khác nhau.
2. **“`Guest.class.getPackageName().equals(Host.class.getPackageName())` là bằng chứng đủ.”** Sai; cần so defining loader.
3. **“Child có thể load `Host` qua parent nên Host thuộc package của child.”** Sai; initiating loader không thay defining loader của `Host`.
4. **“Biên dịch thành công thì JVM không được ném lỗi access.”** Sai; compiler dựa trên view lúc biên dịch, JVM xác minh runtime access.
5. **“`IllegalAccessError` giống `IllegalAccessException`.”** Sai; loại lỗi, nguồn phát sinh và cách điều tra khác nhau.
6. **“Cứ dùng `setAccessible(true)` là sửa được bytecode call.”** Sai; reflection không viết lại phép kiểm tra access tại resolution của lời gọi trực tiếp.
7. **“Public class đồng nghĩa mọi member của nó đều public.”** Sai; `Host` public không làm `Host.secret()` public.
8. **“Chỉ đổi thứ tự classpath không cần xét isolation.”** Sai; thứ tự/nguồn nạp có thể đổi defining loader và tạo lỗi khác.
9. **“Chỉ cần `opens` một JPMS package là cross-loader package-private hợp lệ.”** Sai; module access và run-time package là hai điều kiện khác nhau.
10. **“`NoClassDefFoundError` là kết quả bắt buộc khi dùng package-private giữa loader khác nhau.”** Sai; ví dụ này tìm thấy cả hai class và ném **`IllegalAccessError`**.

## 11. Câu hỏi tự kiểm tra

1. Run-time package được xác định bởi hai thành phần nào? Hai class cùng tên package nhưng khác defining loader có cùng run-time package không?
2. Tại sao `javac` có thể chấp nhận `Guest.callPrivate()` nhưng JVM lại ném `IllegalAccessError`?
3. Nếu `L_child.loadClass("lab.boundary.Host")` ủy quyền thành công cho parent, `Host` thuộc run-time package của loader nào?
4. Trong ví dụ mục 5, vì sao `samePackageName=true` song `sameLoader=false`?
5. Vì sao `Guest.callPublic()` thành công trước khi `Guest.callPrivate()` thất bại?
6. Nếu tình cờ thêm `build/guest` vào system classpath, điều gì có thể xảy ra với loader định nghĩa `Guest`? Vì sao điều đó làm mất giá trị chứng minh của thí nghiệm?
7. `IllegalAccessError` và `IllegalAccessException` khác nhau thế nào?
8. Vì sao đổi package-private member thành `public` cần đi kèm kiểm soát API contract, thay vì sửa tràn lan?
9. Nếu host và plugin cần trao đổi các đối tượng, tại sao một public interface dùng chung được định nghĩa bởi parent loader thường phù hợp?
10. Với named modules, `exports` hoặc `opens` có cho phép hai lớp khác defining loader chia sẻ package-private member chỉ nhờ cùng tên package không?
11. Làm sao bạn phân biệt lỗi access do package-private split với lỗi `NoSuchMethodError` do version mismatch?
12. Trong một dòng log có hai lớp cùng package và mỗi lớp có ClassLoader khác nhau, câu hỏi đầu tiên bạn cần kiểm tra khi có package-private call là gì?

**Tiêu chí hoàn tất:** dự đoán đúng stdout của ví dụ, chứng minh được hai run-time packages khác nhau dù cùng chuỗi package, giải thích được thời điểm `IllegalAccessError` xuất hiện, và đề xuất được một ranh giới API public phù hợp giữa host/plugin.

## 12. Tài liệu chuẩn để đối chiếu

- [JVMS Java SE 21 `5.3` — Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): định danh kiểu và run-time package theo package name + defining loader.
- [JVMS Java SE 21 `5.4.4` — Access Control](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4): kiểm tra quyền truy cập đối với class, field, method; thời điểm sinh `IllegalAccessError`.
- [JLS Java SE 21 `6.6` — Access Control](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.6): khái niệm accessibility ở mức Java language, bao gồm package access.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, parent delegation.
- [Java SE 21 `URLClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): tìm và định nghĩa lớp từ URL/directory/JAR.
- [Java SE 21 `InvocationTargetException` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): reflection bọc exception/error do invoked method ném.

Ví dụ biên dịch với `--release 17` và chạy trên JDK 21 để xác minh stdout; nội dung dùng quy tắc chuẩn áp dụng cho Java 17+. Phạm vi bài là package-private qua các defining loaders, không giả định một framework/plugin cụ thể.