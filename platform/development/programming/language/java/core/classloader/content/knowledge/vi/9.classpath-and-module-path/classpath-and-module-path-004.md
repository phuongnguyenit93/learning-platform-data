# Thứ tự tìm kiếm và lớp trùng tên trong nhiều JAR

## 1. Vấn đề: JVM chọn lớp nào khi nhiều JAR chứa cùng tên?

Giả sử cả `a.jar` và `b.jar` đều chứa file bytecode:

~~~text
demo/dupe/Message.class
~~~

Mã nguồn trong JAR A có thể trả chuỗi `"A"`, còn JAR B trả `"B"`. Nếu một ClassLoader được cấu hình để nhìn thấy **cả hai JAR**, lớp nào sẽ được dùng khi chương trình yêu cầu `demo.dupe.Message`?

Câu trả lời phụ thuộc vào **loader nhận yêu cầu**, **quan hệ ủy quyền tới parent** và **thứ tự tìm kiếm trong những nguồn mà loader đó quản lý**. Với `URLClassLoader` chuẩn, cơ chế phổ biến là:

1. Kiểm tra loader đã nạp class đó chưa.
2. **Parent-first:** hỏi loader cha trước.
3. Nếu cha không tìm thấy, tìm trong các URL của loader con theo thứ tự được cấu hình.
4. Khi một class đã được định nghĩa cho tên đó trong loader, những lần yêu cầu sau trả lại class tương ứng; đổi thứ tự danh sách URL **không tự thay thế class đã nạp**.

“Class trùng tên” có hai kết quả khác nhau cần phân biệt:

- **Một loader duy nhất thấy hai JAR:** thông thường chỉ class ở nguồn **được tìm thấy trước** trở thành class được loader đó định nghĩa; phiên bản nằm ở nguồn sau bị che khuất đối với tên đó.
- **Hai loader riêng biệt tự định nghĩa class cùng tên:** JVM có thể đồng thời tồn tại **hai runtime class khác nhau** mặc dù binary name giống nhau. Bản sắc runtime dựa trên tên nhị phân **và loader đã định nghĩa**, không dựa trên tên JAR.

Đây là nguồn gốc của nhiều lỗi “chạy máy này được, máy kia sai”, thư viện version xung đột, `NoSuchMethodError` hoặc `ClassCastException` khi ứng dụng dùng plugin, application server hoặc classpath chứa các bản JAR chồng chéo.

## 2. Thứ tự tìm kiếm là thứ tự *theo từng loader*

Mô hình parent-first của `ClassLoader.loadClass` thường được diễn đạt:

~~~text
Child.loadClass("demo.dupe.Message")
    │
    ├─ Đã được nạp trong child?
    │      └─ Có → trả Class<?> đã biết
    │
    ├─ Nhờ parent tìm class
    │      └─ Parent thấy → trả class của parent
    │
    └─ Parent không thấy → child.findClass(...)
           ├─ URL đầu tiên có bytecode hợp lệ → dùng class đó
           └─ Tiếp tục tới URL kế tiếp nếu chưa tìm thấy
~~~

Đây là sơ đồ khái niệm cho **ClassLoader tuân parent-first**, không phải lời hứa về mọi loader tùy biến. Một loader child-first có thể đảo thứ tự tra cứu. Java Platform Module System (JPMS) còn áp dụng module resolution/readability và không thể diễn đạt toàn bộ bằng thứ tự JAR trên classpath.

Trong `URLClassLoader` được tạo từ một mảng URL, thứ tự URL quyết định **ưu tiên tìm class và resource trong đường tìm kiếm của chính loader ấy**, khi parent không có kết quả và không có cấu hình đặc biệt khác như manifest `Class-Path` làm mở rộng đường tìm kiếm. Vì thế:

~~~java
// Mã minh họa (cần tạo aUrl, bUrl và parent).
URLClassLoader ab = new URLClassLoader(new URL[] {aUrl, bUrl}, parent);
URLClassLoader ba = new URLClassLoader(new URL[] {bUrl, aUrl}, parent);
~~~

Nếu parent không thấy `demo.dupe.Message`:

- `ab` thường chọn class từ `a.jar`.
- `ba` thường chọn class từ `b.jar`.
- Hai class được định nghĩa bởi **hai loader độc lập**, do đó không phải cùng runtime class.

Nếu parent **đã** thấy `demo.dupe.Message`, cả `ab` lẫn `ba` theo parent-first sẽ thường nhận **class của parent**. Khi đó việc đổi thứ tự URL trong child không thay được kết quả.

## 3. Classpath khi khởi chạy Java và các đường tìm kiếm

Ở chế độ **classpath/unnamed modules** thông thường:

~~~bash
# Linux/macOS: dấu : ngăn cách các entry.
java -cp "a.jar:b.jar:classes" demo.app.Main

# Windows: dấu ; ngăn cách các entry.
java -cp "a.jar;b.jar;classes" demo.app.Main
~~~

Khi **cùng loader ứng dụng** tìm một class trong các entry classpath, vị trí entry thường tạo ra thứ tự ưu tiên: entry phía trước được xét trước khi class chưa nạp. Nếu dùng wildcard `lib/*`, **thứ tự mở rộng các JAR bởi launcher không được đặc tả ổn định**: không thiết kế chương trình dựa trên “tên JAR sắp xếp alphabet” hoặc thứ tự liệt kê thư mục.

Lưu ý:

- Thứ tự classpath không vượt qua **parent delegation**. Class do parent cung cấp thắng các URL nằm trong child trong mô hình parent-first, bất kể tên file.
- Classpath có thể gồm thư mục và JAR. Một thư mục `classes/` chứa class cùng FQCN cũng có thể che JAR sau nó.
- `MANIFEST.MF` có thuộc tính `Class-Path` có thể thêm entry vào đường tìm kiếm của loader/launcher theo cơ chế riêng, nên quan sát mỗi danh sách `-cp` đôi khi chưa đủ để lý giải kết quả.
- Trên Java 9+, system class loader không được đảm bảo là `URLClassLoader`; không cast bừa để sửa URL của system loader đang chạy.
- `--module-path` không phải một danh sách classpath có quy tắc “JAR đứng trước thắng” tương đương. Named modules có cơ chế resolution, package ownership và class loading riêng.
- `Class-Path` của manifest không hoạt động giống lệnh `-cp` trong mọi hoàn cảnh: chỉ có ý nghĩa trong phạm vi các loại URL/JAR và quy tắc được hỗ trợ.

## 4. Bài thực nghiệm Java 17+: hai JAR trùng tên và một parent JAR

Ta tạo ba JAR với **cùng binary name** `demo.dupe.Message` nhưng kết quả khác nhau, và một host **không tham chiếu trực tiếp class này khi biên dịch**. Nhờ vậy host có thể chủ động kiểm tra loại được chọn qua reflection.

### 4.1. Cấu trúc dự án

~~~text
jar-order-demo/
├── host-src/
│   └── demo/host/JarOrderDemo.java
├── a-src/
│   └── demo/dupe/Message.java
├── b-src/
│   └── demo/dupe/Message.java
├── parent-src/
│   └── demo/dupe/Message.java
├── a-resources/
│   └── label.txt
├── b-resources/
│   └── label.txt
└── parent-resources/
    └── label.txt
~~~

Ba file `Message.java` ở **ba thư mục source khác nhau** đều khai báo `package demo.dupe;` và `public class Message`. Chúng được biên dịch **riêng thành ba output directory**, sau đó đóng thành ba JAR độc lập. Không biên dịch chung ba source trùng FQCN vào một lệnh `javac` vì điều đó dẫn tới định nghĩa lớp trùng nhau trong cùng compilation.

### 4.2. Class trong JAR A

File **`a-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "A";
    }
}
~~~

File **`a-resources/label.txt`** chứa chính xác:

~~~text
A
~~~

### 4.3. Class trong JAR B

File **`b-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "B";
    }
}
~~~

File **`b-resources/label.txt`**:

~~~text
B
~~~

### 4.4. Class tương ứng ở JAR của parent

File **`parent-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "PARENT";
    }
}
~~~

File **`parent-resources/label.txt`**:

~~~text
PARENT
~~~

`parent.jar` cho phép thực hiện thêm thí nghiệm về **parent-first precedence** mà không thay đổi host hay hai JAR A/B.

### 4.5. Host: tự chọn URL order và kiểm tra định danh lớp

File **`host-src/demo/host/JarOrderDemo.java`**:

~~~java
package demo.host;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class JarOrderDemo {
    private JarOrderDemo() {
    }

    private static String origin(ClassLoader loader)
            throws ClassNotFoundException, NoSuchMethodException,
            IllegalAccessException, InvocationTargetException {
        Class<?> type = loader.loadClass("demo.dupe.Message");
        return (String) type.getMethod("origin").invoke(null);
    }

    private static String resourceLabel(ClassLoader loader)
            throws IOException {
        try (InputStream stream = loader.getResourceAsStream("label.txt")) {
            if (stream == null) {
                return "(missing)";
            }
            return new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static boolean parentCanLoad(ClassLoader parent) {
        try {
            parent.loadClass("demo.dupe.Message");
            return true;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: JarOrderDemo <a.jar> <b.jar>");
        }

        Path a = Path.of(args[0]).toAbsolutePath().normalize();
        Path b = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(a) || !Files.isRegularFile(b)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL aUrl = a.toUri().toURL();
        URL bUrl = b.toUri().toURL();
        ClassLoader parent = JarOrderDemo.class.getClassLoader();

        // AB và BA là hai loader khác nhau; mỗi loader có URL order riêng.
        try (URLClassLoader ab =
                     new URLClassLoader(new URL[] {aUrl, bUrl}, parent);
             URLClassLoader ba =
                     new URLClassLoader(new URL[] {bUrl, aUrl}, parent)) {

            System.out.println("AB class: " + origin(ab));
            System.out.println("BA class: " + origin(ba));

            System.out.println("AB resource: " + resourceLabel(ab));
            System.out.println("BA resource: " + resourceLabel(ba));

            Class<?> classAB = ab.loadClass("demo.dupe.Message");
            Class<?> classBA = ba.loadClass("demo.dupe.Message");

            System.out.println("AB and BA same Class: "
                    + (classAB == classBA));
            System.out.println("AB defined by child: "
                    + (classAB.getClassLoader() == ab));
            System.out.println("BA defined by child: "
                    + (classBA.getClassLoader() == ba));
            System.out.println("AB load again same Class: "
                    + (classAB == ab.loadClass("demo.dupe.Message")));
            System.out.println("Parent can load duplicate: "
                    + parentCanLoad(parent));
        }
    }
}
~~~

Điểm chủ chốt:

- Host không import `demo.dupe.Message`; nó chỉ biết tên nhị phân dạng chuỗi để thử nạp.
- `ab` có thứ tự URL `[a.jar, b.jar]`, còn `ba` là `[b.jar, a.jar]`.
- Cả hai được tạo với **cùng parent**: loader đã định nghĩa `JarOrderDemo`.
- `origin()` là phương thức `public static`, gọi qua reflection để minh họa class nào thực sự được chọn.
- `resourceLabel()` đọc `label.txt` bằng `getResourceAsStream`. Ví dụ giả định file chỉ có một bản trong mỗi JAR và không có resource cùng tên ở các entry khác ngoài những nguồn đã khai báo.
- `try-with-resources` đóng hai `URLClassLoader` để giải phóng nguồn JAR. `close()` **không buộc JVM unload class ngay**.

## 5. Biên dịch và đóng gói từng JAR

Yêu cầu JDK 17+ có `javac`, `jar` và `java` trên `PATH`. Đứng tại thư mục gốc `jar-order-demo/` đã tạo đủ file như trên.

**Bash (Linux/macOS/Git Bash):**

~~~bash
mkdir -p build/host build/a build/b build/parent dist

javac -encoding UTF-8 -d build/host \
  host-src/demo/host/JarOrderDemo.java

javac -encoding UTF-8 -d build/a a-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/b b-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/parent parent-src/demo/dupe/Message.java

cp a-resources/label.txt build/a/label.txt
cp b-resources/label.txt build/b/label.txt
cp parent-resources/label.txt build/parent/label.txt

jar --create --file dist/a.jar -C build/a .
jar --create --file dist/b.jar -C build/b .
jar --create --file dist/parent.jar -C build/parent .
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/a,build/b,build/parent,dist | Out-Null

javac -encoding UTF-8 -d build/host host-src/demo/host/JarOrderDemo.java

javac -encoding UTF-8 -d build/a a-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/b b-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/parent parent-src/demo/dupe/Message.java

Copy-Item a-resources/label.txt build/a/label.txt
Copy-Item b-resources/label.txt build/b/label.txt
Copy-Item parent-resources/label.txt build/parent/label.txt

jar --create --file dist/a.jar -C build/a .
jar --create --file dist/b.jar -C build/b .
jar --create --file dist/parent.jar -C build/parent .
~~~

Mỗi JAR có class `demo/dupe/Message.class` và resource `label.txt` riêng. Có thể kiểm tra:

~~~bash
jar --list --file dist/a.jar
jar --list --file dist/b.jar
jar --list --file dist/parent.jar
~~~

Các lệnh `jar --list` cũng có thể liệt kê `META-INF/MANIFEST.MF` và các directory entry. Đây là JAR thường, không dùng manifest `Class-Path`, không dùng multi-release JAR và không có module descriptor; do đó kết quả thí nghiệm chỉ phụ thuộc URL order/parent của loader nêu trên.

## 6. Chạy lần 1: parent không có class trùng tên

**Bash hoặc PowerShell:**

~~~bash
java -cp build/host demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Stdout chính xác:**

~~~text
AB class: A
BA class: B
AB resource: A
BA resource: B
AB and BA same Class: false
AB defined by child: true
BA defined by child: true
AB load again same Class: true
Parent can load duplicate: false
~~~

**Giải thích:**

1. Parent là application loader của `JarOrderDemo` và chỉ chứa `build/host`; không có `Message.class`. Khi `ab` hỏi parent, parent không tìm thấy, nên `ab` tìm A trước B và lấy class `Message` của A.
2. Loader `ba` độc lập, tìm B trước A, nên lấy class của B.
3. Hai loader khác nhau **tự định nghĩa** `demo.dupe.Message`; `classAB == classBA` là `false`. Việc cả hai có cùng `getName()` không làm chúng thành cùng runtime type.
4. Gọi `ab.loadClass(...)` lần nữa trả về class đã biết, không tải một phiên bản khác từ B.
5. Đối với resource `label.txt`, `URLClassLoader` hỏi parent trước rồi tìm trong các URL của mình. Khi parent không chứa resource, thứ tự A/B cũng cho ra `A` hoặc `B`.
6. `parentCanLoad(parent)` trả `false` vì parent không tự duyệt URL của các loader con.

**Không đọc kết quả “A thắng” thành quy tắc toàn JVM.** Chính loader `ab` ưu tiên A trong đường tìm kiếm **riêng** của nó; loader `ba` lại ưu tiên B. Nếu có hai loader khác nhau, cả hai class có thể tồn tại cùng lúc.

## 7. Chạy lần 2: parent có class trùng tên

Bây giờ **không sửa code, không sửa JAR, không tạo loader mới bằng cách thay bytecode đang chạy**. Hãy **khởi động một JVM mới** nhưng thêm `dist/parent.jar` vào **application classpath**.

**Bash (Linux/macOS):**

~~~bash
java -cp "build/host:dist/parent.jar" \
  demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/parent.jar" demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Stdout chính xác với cấu hình parent-first mặc định:**

~~~text
AB class: PARENT
BA class: PARENT
AB resource: PARENT
BA resource: PARENT
AB and BA same Class: true
AB defined by child: false
BA defined by child: false
AB load again same Class: true
Parent can load duplicate: true
~~~

**Vì sao cả AB và BA đều nhận PARENT?**

- Khi `ab` và `ba` nhận `loadClass("demo.dupe.Message")`, chúng hỏi parent trước.
- Parent thấy `demo.dupe.Message` từ `dist/parent.jar` trên application classpath và trả class do nó định nghĩa.
- Hai child đều nhận **cùng đối tượng `Class<?>`** của parent; thứ tự A/B bên trong child trở nên không còn tác dụng đối với class name đó.
- Với `label.txt`, parent-first resource lookup cũng tìm thấy resource của parent trước; `getResourceAsStream` trả nội dung `PARENT`.

Điểm thực tế: thay thứ tự URL của child **không đủ** để giải quyết “JAR của host che JAR của plugin”. Nếu thư viện đã có ở parent và loader dùng parent-first, phiên bản parent thường được ưu tiên.

## 8. Điều gì xảy ra khi hai bản class có API không tương thích?

Thí nghiệm A/B chỉ thay đổi chuỗi trả về, nên việc chọn bản nào vẫn chạy được. Trong ứng dụng thật, hai JAR có thể chứa các phiên bản API khác nhau:

~~~java
// Bản v1 (mã minh họa, không phải file trong demo):
public final class Client {
    public static String build(String text) {
        return text;
    }
}

// Bản v2 (mã minh họa):
public final class Client {
    public static String build(String text, int count) {
        return text.repeat(count);
    }
}
~~~

Giả sử caller **được biên dịch với v2** và gọi `Client.build("x", 2)`. Nếu loader runtime lại chọn class v1 (không có method descriptor tương ứng), lần thực thi lời gọi có thể phát sinh `NoSuchMethodError`. Đây là vấn đề **binary compatibility** và quyết định class được nạp, không chỉ là “có file Class trên classpath”.

Các lỗi thường gặp liên quan:

| Triệu chứng | Khả năng thường gặp |
|---|---|
| `NoSuchMethodError` | Bytecode caller và phiên bản class được chọn không có cùng method descriptor |
| `NoSuchFieldError` | Phiên bản class runtime thiếu field mà caller đã biên dịch để truy cập |
| `ClassCastException` | Hai loader đã định nghĩa hai class cùng tên hoặc class khác không phù hợp kiểu đích |
| `LinkageError` | Có xung đột type/loading constraints hoặc không tương thích nhị phân |
| `NoClassDefFoundError` | Class đã được yêu cầu liên kết/khởi tạo nhưng dependency không sẵn có ở runtime hoặc lỗi khởi tạo đã được ghi nhận |
| `ServiceConfigurationError` | Provider sai cấu hình hoặc không tương thích với service type mà host yêu cầu |
| Hành vi khác nhau giữa môi trường | Thứ tự `-cp`/URL, wildcard, dependency transitive hoặc parent loader khác nhau |

**Bước chẩn đoán:** xác định **class thực sự được JVM dùng**, không đoán từ JAR “đã đặt vào thư mục lib”. Kiểm tra classloader topology, classpath/module path và nguồn định nghĩa của class. `Class.getProtectionDomain().getCodeSource()` thường hữu ích khi có CodeSource, nhưng có thể trả `null` và không nên coi là chỉ báo bắt buộc trong mọi môi trường.

## 9. Resource trùng tên và `getResources`

Đối với `URLClassLoader` thông thường:

- `getResource(name)` trả URL của resource **đầu tiên** mà loader tìm được theo chuỗi tra cứu parent-first rồi tới URL path của chính loader.
- `getResources(name)` có thể trả **nhiều URL** (ví dụ cả A lẫn B), thường theo thứ tự tài nguyên ở parent rồi tài nguyên loader con.
- `getResourceAsStream(name)` mở một resource đầu tiên tương ứng; ứng dụng phải đóng stream.
- Với tệp cấu hình ghép từ nhiều JAR, ví dụ `META-INF/services/com.example.Service`, `ServiceLoader` có thể đọc **nhiều** resource descriptor, không đơn giản lấy một file đầu tiên rồi bỏ qua toàn bộ còn lại.

Trong ứng dụng thực tế, thứ tự resource cũng có thể ảnh hưởng tệp cấu hình `log4j2.xml`, `application.properties` hoặc các resource mặc định. Tuy nhiên mỗi framework có quy tắc nạp/gộp cấu hình riêng; **không** mặc định mọi framework dùng đúng logic `getResource` của Java rồi chọn file đầu tiên.

Ví dụ nếu muốn kiểm tra tất cả `label.txt` từ loader AB, dùng đoạn minh họa này bên trong method đã có `ab`:

~~~java
// Mã minh họa, cần ab và import java.util.Enumeration.
java.util.Enumeration<URL> urls = ab.getResources("label.txt");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

Nội dung URL phụ thuộc đường dẫn tuyệt đối nên ví dụ này **không cam kết stdout cụ thể**. Khi ứng dụng cần liệt kê resource trùng, đây là thao tác phù hợp hơn `getResource`. Với resource trong **named modules**, luật encapsulation/`opens` có thể ảnh hưởng khả năng hiển thị.

## 10. Phân biệt ba cấp ưu tiên

| Cấp | Câu hỏi | Ví dụ |
|---|---|---|
| **ClassLoader topology** | Child có hỏi parent trước không? | Parent có `Message` nên A/B trong child đều bị che |
| **URL/classpath order của một loader** | Khi parent không có, nguồn nào được loader xét trước? | `[a.jar, b.jar]` chọn A; `[b.jar, a.jar]` chọn B |
| **Runtime class identity và cache** | Loader đã định nghĩa/từng nhận class nào cho binary name đó? | Yêu cầu `ab.loadClass` lần hai vẫn là class A; loader khác có thể là class B |

Cần tách hai khái niệm thường bị gộp:

**“First found”** là quy tắc tìm kiếm *bên trong một lookup path* tại thời điểm cần tìm class/resource.

**“First loaded/defined”** nói tới trạng thái một loader đối với một class. Sau khi loader đã định nghĩa class, JVM không cho cùng loader tùy ý định nghĩa lại cùng binary name như một bản thay thế; cố định nghĩa lại có thể gây `LinkageError`. Đổi thứ tự URL của loader đang chạy không biến class A đã định nghĩa thành class B.

Nếu muốn thay một version plugin trong cùng JVM, thường tạo **loader mới**, ngừng dùng object/loader cũ, giải phóng references và tài nguyên rồi tạo instance mới. Không có cơ chế đổi class object cũ chỉ bằng sửa JAR trên đĩa.

## 11. Một số tình huống đặc biệt

### 11.1. Wildcard classpath

~~~bash
java -cp "lib/*" demo.app.Main
~~~

Launcher mở rộng `*` thành các JAR phù hợp trong thư mục. **Thứ tự mở rộng không được bảo đảm** theo Javadoc/launcher specification; không cố ý đặt hai bản cùng FQCN vào `lib/` rồi kỳ vọng file `a.jar` thắng `b.jar` vì tên đứng trước. Dùng dependency graph rõ ràng và loại bỏ bản dư thừa.

### 11.2. Multi-release JAR

Một **multi-release JAR** có thể chứa các phiên bản class dành cho những Java release khác nhau dưới `META-INF/versions/...`. Việc chọn bản class khi đọc JAR còn phụ thuộc phiên bản runtime/quy tắc multi-release; nó **khác** với cạnh tranh giữa hai JAR có cùng FQCN.

### 11.3. Named modules và split packages

Khi chạy với `--module-path`, JPMS giải quyết các module theo quan hệ phụ thuộc và luật package/module. Hai module cùng cung cấp một package cho cùng module consumer có thể làm configuration/resolution hoặc compilation thất bại; không có phép tổng quát “module path đứng trước thì class trùng tên thắng”.

### 11.4. Child-first trong plugin containers

Một số application server triển khai child-first cho thư viện của từng ứng dụng để tránh xung đột với host. Khi ấy plugin có thể chủ động chọn bản class trong JAR con trước parent, **nhưng** rất dễ tạo hai runtime interface/DTO cùng tên nếu không “parent-first” riêng cho API dùng chung. Khả năng cô lập dependency cần đi kèm ranh giới kiểu rõ ràng.

### 11.5. Thứ tự compile-time khác runtime

`javac` có thể chọn API từ classpath lúc biên dịch, nhưng `java` khi chạy lại thấy JAR khác do thứ tự dependency khác. Compile thành công **không chứng minh** class runtime có cùng method/field signature. Bộ quản lý dependency (Gradle/Maven) nên khóa/kiểm tra phiên bản và loại bỏ dependency trùng ngoài ý muốn.

## 12. Cách kiểm tra nhanh trên dự án thật

1. **Liệt kê entry chứa class trùng**: kiểm tra JAR với `jar --list --file path/to/library.jar` hoặc công cụ phân tích dependency. Lệnh `jar --list` chỉ chứng minh **file có class**, không chứng minh JVM đã dùng bản ấy.
2. **Ghi lại runtime ClassLoader**: gọi `SomeClass.class.getClassLoader()`; so sánh identity loader bằng `==`, không phụ thuộc chuỗi `toString()`.
3. **Xác định nguồn bytecode**: nếu có, xem `SomeClass.class.getProtectionDomain().getCodeSource()`; có thể là `null` đối với một số loader/class.
4. **Kiểm tra launch config**: `java -cp`, IDE classpath, test runtime classpath, `java.system.class.loader`, module path, agent và plugin loader.
5. **Kiểm tra thứ tự có ý nghĩa hay không**: nếu parent đã có class, đảo thứ tự child URL thường không đổi kết quả; nếu không có parent, URL order có thể quyết định kết quả.
6. **Đối chiếu dependency version**: nếu thấy `NoSuchMethodError`, kiểm tra class đã thực sự được nạp có signature mong đợi bằng `javap` hoặc công cụ tương đương; đừng chỉ thêm JAR ngẫu nhiên.
7. **Tách API chung khỏi implementation**: host/plugin giao tiếp bằng kiểu do parent chung định nghĩa để tránh cast lỗi giữa nhiều loader.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| “Đặt JAR mới cuối `-cp` sẽ được ưu tiên” | Trong cùng classpath thông thường, entry đứng trước thường được tìm trước | Làm rõ thứ tự và loại bản trùng |
| “Đảo thứ tự child URL chắc chắn đổi class” | Parent có thể đã nạp hoặc tìm được class | Kiểm tra parent và nơi class được định nghĩa |
| “Một JVM không thể có hai class cùng FQCN” | Hai defining loader khác nhau có thể tạo hai runtime type khác nhau | So sánh `Class<?>` và `getClassLoader()` |
| “URLClassLoader luôn chọn JAR theo tên alphabet” | Thứ tự đến từ mảng URL, không phải phép sort tên file | Truyền thứ tự URL tường minh |
| “Wildcards `lib/*` có thứ tự ổn định” | Quy tắc mở rộng wildcard không bảo đảm thứ tự | Loại bỏ class trùng, quản lý classpath có kiểm soát |
| “Class có trong một JAR nên chắc chắn JVM đã nạp nó” | Có thể bị che bởi class từ JAR/parent khác | Kiểm tra defining loader và CodeSource nếu có |
| “Classpath Java 17 và module path giống nhau” | JPMS có luật module/package, visibility và resolution khác | Phân biệt classpath và `--module-path` |
| “Thay JAR trên đĩa sẽ cập nhật class đã tải” | Class object/bytecode đã được loader định nghĩa không tự thay | Tạo loader mới hoặc khởi động lại tiến trình |

## 14. Tự kiểm tra

**Câu 1.** Parent không có `demo.dupe.Message`. Một loader con có URL theo thứ tự `[a.jar, b.jar]`, mỗi JAR chứa cùng FQCN. Theo `URLClassLoader` chuẩn trong ví dụ, implementation nào được chọn?

**Đáp án:** Bản trong `a.jar`, vì đây là URL đầu tiên có class được yêu cầu.

**Câu 2.** Hai loader con độc lập lần lượt nhận `[a.jar, b.jar]` và `[b.jar, a.jar]`. Hai kết quả `Class<?>` có bằng nhau bằng `==` không?

**Đáp án:** Không, khi mỗi loader tự định nghĩa class; bản sắc runtime là binary name + defining loader.

**Câu 3.** Parent có class cùng tên. Nếu đảo URL A/B ở child mà không thay parent, kết quả thường thế nào?

**Đáp án:** Cả hai child đều nhận class do parent định nghĩa (parent-first); đổi thứ tự URL bên trong child không đủ đổi class.

**Câu 4.** `child.getResources("label.txt")` có thể thấy mấy resource khi hai JAR cùng chứa file đó?

**Đáp án:** Nó có thể liệt kê **hai URL** của A và B (và thêm resource từ parent nếu có). `getResource` chỉ trả một kết quả đầu tiên.

**Câu 5.** Vì sao mã biên dịch đúng nhưng gặp `NoSuchMethodError` khi chạy?

**Đáp án:** Caller có thể được biên dịch với class ở JAR v2, trong khi loader runtime chọn class ở JAR v1 không còn method descriptor cần gọi.

**Câu 6.** Có nên dùng `-cp "lib/*"` để bảo đảm phiên bản thư viện được chọn theo tên JAR không?

**Đáp án:** Không. Thứ tự mở rộng wildcard không được bảo đảm. Tốt nhất xử lý dependency trùng và đảm bảo version rõ ràng.

## 15. Nguồn tham khảo

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, class identity và tài nguyên.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): đường tìm kiếm URL và cách đóng loader.
- [Java SE 17 — Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--class-path`, dấu phân cách và wildcard expansion.
- [Java Virtual Machine Specification 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): khái niệm defining loader và loading constraints.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): thuộc tính manifest `Class-Path` và cấu trúc JAR.
- [Java SE 17 — Class#getProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getProtectionDomain()): thông tin domain/source khi khả dụng.

**Điểm cần nhớ:** Quyết định JAR nào “thắng” phải xét **parent delegation trước**, **thứ tự tìm class trong loader cụ thể sau**, và **class đã được định nghĩa/cached**. Nếu có nhiều ClassLoader, hai class cùng FQCN vẫn có thể cùng tồn tại như hai runtime type khác nhau.