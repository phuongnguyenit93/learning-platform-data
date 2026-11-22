# Wildcard trong classpath và giới hạn tìm kiếm

> **Chủ đề:** Java Core → ClassLoader → Đường dẫn tìm kiếm. Bài học làm rõ cú pháp `*` trong **application classpath**, đối tượng được tìm kiếm, thời điểm mở rộng wildcard, giới hạn thư mục/JAR, thứ tự nạp lớp và khác biệt với module path, manifest và custom class loaders. Ví dụ chạy trên Java 17+.

## 1. Vấn đề thực tế: vì sao có lib/* nhưng vẫn ClassNotFoundException?

Giả sử ứng dụng có thư mục:

```text
project/
├── app-classes/
│   └── demo/App.class
└── libs/
    ├── core.jar
    ├── helper.JAR
    ├── tools.zip
    ├── loose/Loose.class
    └── nested/
        └── plugin.jar
```

Một lệnh quen thuộc:

```bash
java -cp "app-classes:libs/*" demo.App
```

Theo hợp đồng của Java launcher, phần tử `libs/*` được mở rộng thành **các file có đuôi `.jar` hoặc `.JAR` nằm trực tiếp trong `libs`**. Nó không có nghĩa “tìm mọi file và mọi thư mục con”.

Trong sơ đồ:

| Đối tượng | `libs/*` có đưa vào classpath trực tiếp? | Vì sao |
| --- | --- | --- |
| `libs/core.jar` | Có | JAR ngay trong thư mục được chỉ định. |
| `libs/helper.JAR` | Có | Hỗ trợ đuôi `.JAR`. |
| `libs/tools.zip` | Không | Wildcard chỉ liệt kê JAR; vẫn có thể đưa ZIP vào classpath bằng đường dẫn tường minh nếu phù hợp. |
| `libs/loose/Loose.class` | Không | `*` không tự bổ sung thư mục chứa loose class files. |
| `libs/nested/plugin.jar` | Không | Không tìm JAR trong thư mục con theo đệ quy. |
| `app-classes/demo/App.class` | Có, do `app-classes` | Đây là một phần tử classpath riêng, không phải kết quả của `libs/*`. |

Vì vậy, nếu `demo.App` cố `Class.forName("plugin.Main")` nhưng class đó chỉ nằm trong `libs/nested/plugin.jar`, lệnh trên **không tự tìm thấy** nó. Tương tự, `loose.Loose` dưới `libs/loose/Loose.class` cần bổ sung **`libs`** như một *directory classpath root*.

## 2. Classpath là danh sách root tìm kiếm, không phải phép quét mọi class

Classpath (`-cp`, `-classpath` hoặc `--class-path`) gồm các phần tử chỉ đến:

- **Thư mục gốc** chứa cấu trúc package; ví dụ `classes` chứa `classes/com/acme/Thing.class`, tên nhị phân là `com.acme.Thing`.
- **JAR file** lưu class/resource theo entry name tương ứng; ví dụ `lib/tool.jar` chứa `com/acme/Thing.class`.
- **ZIP archive** khi được khai báo tường minh làm classpath element; bản thân dấu `*` không liệt kê ZIP.

Java launcher dùng các phần tử này để thiết lập môi trường tìm class/resource của ứng dụng. Nó **không** chạy trước một tác vụ “nạp tất cả class từ mọi JAR”; loader thường tìm và định nghĩa class **khi chương trình cần**. Có một path tới JAR không bảo đảm mọi class trong JAR sẽ được nạp, liên kết, khởi tạo hoặc truy cập được.

Chuyển tên nhị phân thành đường dẫn resource:

```text
Binary name:      com.acme.Thing
Class entry:      com/acme/Thing.class

Root:             classes
Full path:        classes/com/acme/Thing.class

Root:             lib/tool.jar
JAR entry:        com/acme/Thing.class
```

Đừng đặt `classes/com/acme` vào classpath rồi mong loader tìm `com.acme.Thing`: root đúng phải là `classes`. Việc tìm kiếm tài nguyên (`getResource`, `getResources`) có quy tắc riêng và thường dùng đường dẫn dấu `/`; không nhập nhằng resource path với binary name.

## 3. Cú pháp wildcard chính xác

Đối với Java launcher:

- `libs/*`: mọi file JAR trực tiếp trong `libs` có đuôi `.jar` hoặc `.JAR`.
- `*`: mọi JAR trực tiếp trong **working directory hiện tại** (nếu đường dẫn classpath phần tử chỉ là `*`).
- `classes:libs/*` (Linux/macOS), hoặc `classes;libs/*` (Windows): kết hợp một thư mục classes với JAR wildcard.
- `libs/*:libs` hoặc `libs;libs/*`: kết hợp cả JARs và loose classes ở thư mục `libs`; thứ tự hai phần tử có thể ảnh hưởng khi class/resource trùng tên.

Đặc tả **không** cho phép hiểu `*` như glob tổng quát. Những cách dùng không có semantics “liệt kê tự động” tương ứng của classpath wildcard:

| Cú pháp muốn dùng | Sai kỳ vọng | Thay bằng |
| --- | --- | --- |
| `libs/foo*.jar` | Match theo prefix `foo` | Liệt kê file JAR cụ thể, hoặc quản lý dependency bằng công cụ build. |
| `libs/**/*.jar` | Tìm JAR đệ quy | Tạo classpath từ từng thư mục/JAR được phép, hoặc dùng build tool. |
| `libs/*/plugin.jar` | Tìm trong mọi thư mục con | Nêu rõ `libs/nested/plugin.jar` hoặc root classpath khác. |
| `libs/*` | Tìm mọi `.class` rời ở `libs` | Thêm `libs` thành phần tử riêng. |
| `libs/*` | Tìm `.zip` trong `libs` | Thêm đường dẫn ZIP cụ thể. |
| `libs/*` | Tìm thư viện trong các JAR lồng ở bên trong JAR khác | Sử dụng cơ chế loader đóng gói phù hợp; Java launcher thông thường không giải nén nested JAR tự động. |

JAR bắt đầu bằng dấu chấm (*hidden file*) vẫn có thể được liệt kê nếu phù hợp đuôi JAR. Wildcard mở rộng được xử lý **sớm bởi launcher trước khi chạy `main`**, không phải cú pháp động mà `ClassLoader.loadClass` phân tích mỗi lần tìm class.

**Thứ tự JAR trong một wildcard không được bảo đảm.** Ngay cả khi `libs` có `a.jar` và `b.jar`, đừng suy luận cái nào được xét trước chỉ từ tên file. Nếu cả hai JAR chứa `com.acme.Widget` khác phiên bản, kết quả có thể phụ thuộc môi trường hoặc thứ tự mở rộng. Muốn thứ tự ưu tiên xác định, hãy liệt kê JAR rõ ràng hoặc dùng cơ chế dependency resolution có kiểm soát.

## 4. Ký tự phân cách khác nhau giữa Linux/macOS và Windows

Một phần tử wildcard giữ nguyên `libs/*` ở hai hệ điều hành; khác biệt quan trọng là **ký tự phân cách các phần tử classpath**:

| Hệ điều hành | Separator | Lệnh minh họa |
| --- | --- | --- |
| Linux/macOS | `:` | `java -cp "classes:libs/*" demo.App` |
| Windows PowerShell/CMD | `;` | `java -cp "classes;libs/*" demo.App` |

Dùng dấu nháy kép quanh **toàn bộ chuỗi classpath**, đặc biệt trong shell Unix: nếu để `*` trần, **shell có thể mở rộng nó trước Java launcher**, khiến dòng lệnh bị tách/diễn giải khác ý định. Ví dụ đáng tin:

```bash
java --class-path "classes:libs/*" demo.App
```

Trên Windows:

```powershell
java --class-path "classes;libs/*" demo.App
```

Đường dẫn tương đối trong classpath được diễn giải dựa vào **working directory khi khởi chạy**, không tự động dựa theo vị trí file `.class` hay thư mục chứa JAR. Nếu mở IDE, service/container hoặc chạy script từ một thư mục khác, `libs/*` có thể trỏ vào chỗ khác. Khi debug, hãy kiểm tra working directory:

```java
System.out.println(System.getProperty("user.dir"));
```

Đây là snippet để đặt trong method; `user.dir` chỉ hỗ trợ chẩn đoán ngữ cảnh đường dẫn, không bảo đảm có thể cập nhật classpath đang chạy bằng việc gán lại property.

## 5. Thời điểm wildcard được mở rộng và ý nghĩa java.class.path

Java launcher mở rộng `libs/*` thành một chuỗi các JAR path cụ thể **trước khi `main` bắt đầu**. Vì vậy, trong chương trình có thể xem:

```java
System.out.println(System.getProperty("java.class.path"));
```

Ví dụ `libs` có `a.jar` và `b.jar` thì có thể xuất hiện một chuỗi tương đương với:

```text
classes:libs/a.jar:libs/b.jar
```

Đây chỉ là **một thứ tự minh họa**, không phải output cố định: thứ tự JAR có thể khác; trên Windows separator là `;`. Quan trọng hơn, giá trị `java.class.path` có thể đã là **danh sách mở rộng**, trong khi `System.getenv("CLASSPATH")` (nếu có) chỉ là chuỗi môi trường ban đầu.

Đừng coi `java.class.path` là một API thay đổi classpath tại runtime:

- `System.setProperty("java.class.path", "...")` chỉ sửa **giá trị property trong process**; nó **không có hợp đồng** yêu cầu application class loader cập nhật các nguồn đang dùng.
- Custom loaders, plugin JARs nạp riêng, manifest dependencies và named modules có thể nằm ngoài chuỗi này.
- Trên JDK 9+, application loader tích hợp mặc định không phải `URLClassLoader`; đừng ép `ClassLoader.getSystemClassLoader()` thành `URLClassLoader` chỉ để gọi `getURLs()`.
- JVM có thể đang chạy trong container/framework với loader delegation không giống môi trường chạy `java` thuần.

Khi cần **thay đổi dependencies**, hãy quyết định ở launch/build time hoặc tạo loader riêng có nguồn rõ ràng, không sửa property rồi chờ lớp mới xuất hiện.

## 6. Ví dụ Java 17+ tái tạo ba giới hạn tìm kiếm

Thí nghiệm dùng một JAR ngay trong thư mục `libs`, một JAR nằm trong thư mục con và một file `.class` rời. Chương trình kiểm tra bằng `Class.forName`, không dùng thư viện ngoài JDK.

### Cấu trúc source

Tạo các file:

```text
src/demo/PathDemo.java
src/greet/example/Greeter.java
src/extra/deep/Extra.java
src/loose/loose/Loose.java
```

**File `src/demo/PathDemo.java`:**

```java
package demo;

public class PathDemo {
    public static void main(String[] args) {
        for (String name : new String[]{
                "example.Greeter", "deep.Extra", "loose.Loose"}) {
            try {
                Class.forName(name);
                System.out.println(name + ": FOUND");
            } catch (ClassNotFoundException e) {
                System.out.println(name + ": MISSING");
            }
        }
    }
}
```

**File `src/greet/example/Greeter.java`:**

```java
package example;
public class Greeter {}
```

**File `src/extra/deep/Extra.java`:**

```java
package deep;
public class Extra {}
```

**File `src/loose/loose/Loose.java`:**

```java
package loose;
public class Loose {}
```

### Chuẩn bị artifacts và chạy (Linux/macOS)

Đứng tại thư mục chứa `src`. Biên dịch ba class thành ba vị trí khác nhau rồi đóng gói hai JAR:

```bash
mkdir -p libs/nested
javac -d app-classes src/demo/PathDemo.java
javac -d build/greet src/greet/example/Greeter.java
javac -d build/extra src/extra/deep/Extra.java
javac -d libs src/loose/loose/Loose.java
jar --create --file libs/greet.jar -C build/greet .
jar --create --file libs/nested/extra.jar -C build/extra .

java -cp "app-classes:libs/*" demo.PathDemo
```

**Stdout chính xác của lần chạy thứ nhất, đã kiểm chứng trên OpenJDK 21:**

```text
example.Greeter: FOUND
deep.Extra: MISSING
loose.Loose: MISSING
```

Giải thích: `example.Greeter` nằm trong `libs/greet.jar` (JAR ngay trong `libs`), còn `deep.Extra` nằm trong `libs/nested/extra.jar` và `loose.Loose` nằm trong `libs/loose/Loose.class`. Cả hai nguồn sau không được `libs/*` tự động liệt kê.

Chạy lần hai, **nêu thêm** wildcard cho thư mục con và root của loose class:

```bash
java -cp "app-classes:libs/*:libs/nested/*:libs" demo.PathDemo
```

**Stdout chính xác của lần thứ hai:**

```text
example.Greeter: FOUND
deep.Extra: FOUND
loose.Loose: FOUND
```

Mã nguồn không thay đổi; **chỉ cấu hình đường tìm class khác đi**. Đây là bằng chứng rằng mỗi phần tử classpath tạo một root tìm kiếm và `*` không quét đệ quy.

### Chạy tương đương trên Windows PowerShell

Sau khi tạo cùng cấu trúc source, chuẩn bị `libs\nested` (nếu chưa có) và chạy các lệnh `javac`/`jar` như trên; PowerShell cũng chấp nhận dấu `/` cho tên file trong lệnh Java. Các lệnh chạy ứng dụng là:

```powershell
java -cp "app-classes;libs/*" demo.PathDemo
java -cp "app-classes;libs/*;libs/nested/*;libs" demo.PathDemo
```

Kết quả `FOUND/MISSING` giống hai lần chạy trên. Không đổi dấu `:` thành `;` ở bên trong package name, binary class name hoặc resource path; separator này **chỉ dùng giữa các classpath elements**.

## 7. Thứ tự classpath, class trùng tên và resource trùng tên

Classpath thường được tổ chức thành **một danh sách có thứ tự**. Khi nguồn tương đương chứa cùng tên class, thứ tự đường đi và delegation ảnh hưởng class nào được tìm thấy:

```text
-cp "app-classes:lib/new.jar:lib/old.jar"

- app-classes trước
- new.jar sau
- old.jar cuối
```

Ở ví dụ minh họa này, nếu `new.jar` và `old.jar` cùng chứa `com/acme/Client.class` thì đường đi classpath của loader mặc định thường ưu tiên entry ở phía trước **nếu delegation tới parent không nạp class đó trước**. Nhưng nếu dùng `lib/*` thay cho hai tên file tường minh, **thứ tự giữa JAR trong wildcard là không xác định theo contract**.

Với các class có cùng binary name, định danh runtime còn phụ thuộc **defining class loader**. Nhiều loader khác nhau có thể nạp hai class cùng tên và tạo hai kiểu không tương thích; wildcard classpath không hợp nhất class được loader riêng định nghĩa.

Resources cũng có rủi ro trùng tên:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader != null) {
    var resources = loader.getResources("config.properties");
    while (resources.hasMoreElements()) {
        System.out.println(resources.nextElement());
    }
}
```

Đoạn này là snippet trong method có `throws IOException` hoặc xử lý exception. `getResources` có thể liệt kê nhiều URL nếu tài nguyên trùng tên nằm trong các nguồn loader tìm thấy; thứ tự và tập hợp phụ thuộc loader/module và thứ tự classpath thực tế. Nếu chỉ dùng `getResource`, thường lấy một tài nguyên được tìm trước theo quy tắc loader, nên **có thể lấy nhầm bản cấu hình** khi nhiều JAR đóng cùng file `config.properties`.

Đừng giải quyết collision chỉ bằng cách đổi tên file JAR theo thứ tự alphabet rồi dựa vào wildcard; tốt hơn là loại dependency trùng, đặt resource ở namespace riêng, hoặc cấu hình thứ tự classpath rõ ràng.

## 8. CLASSPATH, -cp, java -jar và JAR Manifest

### CLASSPATH environment variable

Nếu không dùng `-cp`/`-classpath`/`--class-path`, Java launcher có thể lấy classpath từ biến môi trường `CLASSPATH`. Classpath wildcard được hỗ trợ trong biến này tương tự khi truyền tùy chọn `-cp`.

Tuy vậy, **khi có tùy chọn `-cp` tường minh, nó ghi đè `CLASSPATH`**, không tự nối vào biến môi trường. Với ứng dụng/CI, cấu hình `-cp` tường minh hoặc dùng build tool thường rõ ràng hơn là phụ thuộc biến môi trường toàn máy.

### Khi dùng java -jar

`java -jar app.jar` khởi động một executable JAR theo `Main-Class` của manifest. Theo tài liệu launcher, trong chế độ này **những classpath setting khác bị bỏ qua**. Ví dụ:

```bash
java -cp "libs/*" -jar app.jar
```

Không bảo đảm nạp `libs/*` cho ứng dụng; cấu hình `-cp` không có tác dụng theo cách người viết lệnh dễ kỳ vọng. Nếu muốn tự kiểm soát classpath, dùng dạng:

```bash
java -cp "app.jar:libs/*" demo.Main
```

Với điều kiện `demo.Main` là tên nhị phân của main class, đây là lệnh Linux/macOS. Trên Windows dùng `"app.jar;libs/*"`. Đây là mẫu cấu hình, **không phải một chương trình độc lập**; tên JAR và main class phải được thay bằng artifact thật.

Một JAR executable cũng có thể khai báo dependencies bằng **`Class-Path` trong manifest** hoặc dùng launcher/loader riêng của framework. Các cơ chế ấy khác Java classpath wildcard.

### Class-Path trong JAR manifest

Ví dụ manifest:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/a.jar lib/b.jar
```

Header này liệt kê các URL tương đối so với JAR chứa manifest. **Không hỗ trợ `*` wildcard** như trên command line: `Class-Path: lib/*` không có nghĩa load mọi JAR trong `lib`. Cần ghi từng JAR hợp lệ hoặc dùng công cụ đóng gói/launcher hỗ trợ mô hình dependencies của ứng dụng.

Các đường manifest còn chịu quy tắc chuẩn hóa, giới hạn URL/path và truy cập của JAR Specification; không tự suy từ chúng thành phép duyệt file system không giới hạn.

## 9. Classpath wildcard khác module path

Từ Java 9, JPMS thêm **module path**, được chỉ định bởi `--module-path` hoặc `-p`:

```bash
java --module-path mods --module com.acme.app/com.acme.Main
```

Classpath và module path giải quyết hai phạm vi khác nhau:

| Nội dung | Classpath | Module path |
| --- | --- | --- |
| Tham số | `-cp`, `-classpath`, `--class-path` | `--module-path` hoặc `-p` |
| Khả năng liệt kê JAR ngay thư mục với `libs/*` | Có, là wildcard của classpath | **Không nên áp dụng cú pháp wildcard classpath** để đoán cách tìm module. |
| Thư mục chứa nhiều artifacts | Với classpath, phải liệt kê JAR hoặc `libs/*`; bản thân `libs` là root class files | Với module path, một thư mục **chứa modules** có thể là một phần tử module path. |
| Cách module được dùng | Classpath classes thuộc unnamed module của loader phù hợp | Named modules phải được phát hiện, giải quyết (`resolution`) và có readability/exports phù hợp. |
| Tìm kiếm | Theo classpath entries và loader behavior | Theo module finder/graph, module layers và class loaders liên quan. |

Thường chỉ cần `--module-path mods` nếu `mods` là thư mục chứa các modular JAR/exploded modules; không viết `mods/*` theo thói quen classpath. Ngoài đường dẫn tồn tại, named module còn phải được **resolved** vào configuration; module chỉ nằm trong thư mục không có nghĩa mọi class của nó tự nạp hoặc mọi package được export.

Classpath wildcard không bypass `module-info.java`, `exports`, `opens`, module readability hoặc kiểm tra truy cập. Nếu thấy `ClassNotFoundException` hoặc `IllegalAccessError` với named modules, hãy phân biệt lỗi đường tìm và lỗi cấu hình/khả năng truy cập module.

## 10. Giới hạn thực sự của phạm vi tìm kiếm do class loader quyết định

Tùy chọn `-cp` thiết lập đường tìm cho application loader của môi trường launcher thông thường; JVM còn có bootstrap/platform loader và có thể có nhiều **custom loaders**.

Mô hình hay gặp:

```text
Code gọi Class.forName / loadClass
             |
             v
          Caller loader
             |
             | parent-first delegation nếu loader dùng chính sách đó
             v
       Parent / platform / bootstrap
             |
             '--- lớp ở ứng dụng / classpath do loader phù hợp quản lý
```

Dù `libs/greet.jar` có được mở rộng vào application classpath, **một plugin loader bị cô lập có thể không nhìn thấy nó** nếu không delegate/không sử dụng nguồn tương ứng. Ngược lại, một custom `URLClassLoader` có thể có các URL/JAR riêng **không xuất hiện** trong `java.class.path`.

Các API quan trọng:

- `ClassLoader.getSystemClassLoader()`: thường là application loader, nhưng kiểu triển khai không được Java SE cam kết; có thể tùy chỉnh.
- `clazz.getClassLoader()`: biết **defining loader** của kiểu `clazz`; trả `null` cho lớp bootstrap như `java.lang.String`.
- `Thread.currentThread().getContextClassLoader()`: context loader, hay được SPI/framework dùng; có thể khác system loader hoặc `null`.
- `Class.forName(name, false, chosenLoader)`: chủ động yêu cầu nạp theo loader chỉ định, **không khởi tạo** do lời gọi này.
- `loader.getResource("com/acme/config.properties")` và `getResources`: truy vấn resources, không bảo đảm tìm mọi nguồn module/JAR ngoài phạm vi loader.

Ngoài tìm được bytes, JVM phải kiểm tra tên, class-file version, linking, dependency, visibility và một số package/module access rules. Class có thể nằm trong JAR **nhưng vẫn không sử dụng được** vì dependency transitively bị thiếu, API bị đổi, conflict loader hoặc module access.

Một launcher/framework đóng gói JAR lồng trong một executable JAR có thể tự triển khai loader để đọc chúng; **Java launcher classpath wildcard thông thường không tự mở JAR nằm bên trong một JAR khác**.

## 11. Các lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException: plugin.Main` | `plugin.jar` ở `libs/nested`; `libs/*` không quét đệ quy. | Thêm `libs/nested/*` hoặc path tới JAR đó. |
| `ClassNotFoundException: loose.Loose` | Chỉ dùng `libs/*`; file `libs/loose/Loose.class` không nằm trong JAR. | Thêm classpath root `libs`. |
| `Could not find or load main class demo.App` | Không đưa root chứa `demo/App.class` vào classpath hoặc launch từ working directory khác. | Thêm `app-classes` và kiểm tra package path. |
| Chạy trên Linux đúng, Windows lỗi | Dùng `:` thay vì `;` giữa các classpath elements. | Dùng separator của OS, đặt classpath trong dấu nháy. |
| Chạy khi gọi trực tiếp đúng, script shell lỗi | Shell mở rộng `*` hoặc quote classpath sai. | Quote toàn bộ `-cp` value, kiểm tra câu lệnh thực thi. |
| `NoClassDefFoundError` khi code tham chiếu lớp | Thiếu dependency transitively, lỗi initialization hoặc binary compatibility. | Đọc `Caused by`; kiểm tra runtime JAR và loader, không chỉ main JAR. |
| Resource bị nạp từ JAR khác | Có nhiều entry resource trùng, wildcard JAR enumeration order bất định. | Sửa xung đột / liệt kê classpath xác định. |
| `java -jar` không nhận JAR khai báo ở `-cp` | Classpath settings khác bị bỏ qua khi dùng `-jar`. | Dùng manifest `Class-Path`, launcher đúng, hoặc chạy bằng tên main class với `-cp`. |
| Manifest có `Class-Path: lib/*` nhưng dependency thiếu | Header không có wildcard expansion của launcher. | Liệt kê URL JAR cụ thể. |
| Thêm JAR sau startup nhưng loader không thấy | Wildcard đã mở rộng trước khi chạy `main`, loader có nguồn tìm cố định. | Restart với classpath mới hoặc thiết kế loader động riêng. |
| `ClassCastException` giữa hai kiểu có cùng tên | Hai defining class loaders khác nhau. | Kiểm tra `clazz.getClassLoader()`, chia sẻ API qua parent phù hợp. |
| JAR có class nhưng module vẫn báo access error | Visibility/readability/exports/opens của JPMS. | Kiểm tra module configuration thay vì mở rộng classpath ngẫu nhiên. |

### Quy trình debug có thể lặp lại

1. In **lệnh Java thật** trong script/container/IDE, version `java -version`, working directory, các giá trị `-cp` và `CLASSPATH`.
2. Quan sát `System.getProperty("java.class.path")` để thấy các classpath entries đã được khởi động; nhớ rằng nó không mô tả mọi module/custom loader.
3. Kiểm tra nội dung JAR bằng `jar --list --file libs/greet.jar` (hoặc `jar tf libs/greet.jar`). Tìm đúng entry `example/Greeter.class`, phân biệt archive root với package path.
4. Kiểm tra xem JAR nằm **ngay trong** thư mục wildcard hay trong subdirectory; phân biệt `.jar/.JAR` với `.zip` và loose class.
5. Nếu có duplicate classes/resources, thử **liệt kê từng JAR theo thứ tự tường minh**; xử lý conflict qua dependency graph thay vì dựa vào wildcard.
6. Nếu vẫn lỗi, so sánh loader của caller và kiểu đang cần, parent delegation và cấu hình module; đừng cho rằng JAR thấy được ở OS sẽ tự thấy được qua mọi loader.
7. Với HotSpot, có thể dùng `-Xlog:class+load=info` để chẩn đoán class loading, nhưng log **không bảo đảm** cung cấp toàn bộ quá trình resource resolution hay mọi đường tìm không thành công.

Ví dụ lệnh chẩn đoán (Linux/macOS; thay tên class thực):

```bash
jar tf libs/greet.jar
java -Xlog:class+load=info -cp "app-classes:libs/*" demo.PathDemo
```

`-Xlog` in thêm nhiều dòng JVM, vì vậy **không dùng output của lệnh này làm đầu ra chính xác trong thí nghiệm mục 6**.

## 12. Tự kiểm tra

1. **`libs/*` có nạp `libs/sub/helper.jar` không?** Không, wildcard classpath không duyệt đệ quy.
2. **`libs/*` có bao gồm `libs/Thing.class` không?** Không, `*` dùng để liệt kê các file JAR; muốn loose class thì thêm `libs`.
3. **Thứ tự `libs/a.jar` và `libs/b.jar` trong mở rộng wildcard có cố định không?** Không được đặc tả; liệt kê JAR tường minh nếu thứ tự quan trọng.
4. **Tại sao `System.getProperty("java.class.path")` có thể không còn chứa `*`?** Launcher mở rộng wildcard trước khi `main` chạy.
5. **`java -cp "libs/*" -jar app.jar` có bảo đảm nạp JAR từ `libs` không?** Không. Chế độ `-jar` bỏ qua classpath settings khác.
6. **Có thể viết `Class-Path: libs/*` trong manifest để liệt kê JAR không?** Không; manifest `Class-Path` không dùng launcher wildcard.
7. **`--module-path mods` khác `-cp "mods/*"` ở điểm nào?** Một bên cấu hình finder/graph cho named modules, bên kia mở rộng các JAR thành classpath entries cho các lớp ứng dụng phù hợp.
8. **Tại sao chương trình có JAR đúng mà vẫn `ClassNotFoundException`?** Có thể sai working directory, binary name, loader, module visibility hoặc dependency; phải xem đường đi thực và code triggering.
9. **Nếu thay `java.class.path` bằng `System.setProperty` rồi chạy lại `Class.forName`, JVM phải nhìn thấy JAR mới?** Không có hợp đồng như vậy.
10. **Hai plugin loaders cùng nhìn thấy một file JAR có chắc chắn chia sẻ cùng class identity?** Không. Nếu chúng tự define cùng binary name riêng, đó là hai kiểu runtime khác nhau.

## 13. Tài liệu chuẩn

- [Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--class-path`, `-jar`, wildcard classpath và module path.
- [Oracle — Understanding class path wildcards](https://docs.oracle.com/javase/8/docs/technotes/tools/windows/classpath.html): wildcard chỉ tìm JAR, không đệ quy, thứ tự không bảo đảm, hành vi `CLASSPATH` và manifest.
- [Java SE 21 — `javac`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-cp`, `--class-path`, source/class output roots.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Class-Path` trong manifest và URL tương đối.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource`, `getResources`, parent delegation.
- [Java SE 21 — Module System / `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module configuration và class loaders của named modules.
