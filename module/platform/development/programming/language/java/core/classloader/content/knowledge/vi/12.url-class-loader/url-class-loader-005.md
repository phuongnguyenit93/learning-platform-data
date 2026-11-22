# getURLs và giới hạn của addURL trong URLClassLoader

> **Ngữ cảnh:** Java Core → ClassLoader → URLClassLoader. Bài này giải thích `URLClassLoader.getURLs()` phản ánh điều gì, tại sao `addURL(URL)` là `protected`, khi thêm URL có tác dụng và những giới hạn quan trọng về parent delegation, class identity, thời điểm nạp lớp, đóng loader và sự khác biệt với application classpath. Các ví dụ dùng API chuẩn Java 17+.

## 1. Hai API trông đơn giản nhưng dễ bị hiểu sai

`java.net.URLClassLoader` là một `ClassLoader` dùng các URL làm **đường tìm class và resource**. URL có thể trỏ đến thư mục chứa cây package, tệp JAR hoặc nguồn thích hợp mà implementation hỗ trợ.

Hai method chính:

```java
public URL[] getURLs();
protected void addURL(URL url);
```

- **`getURLs()`** trả về **mảng đường tìm URL của chính instance URLClassLoader đó**, gồm các URL ban đầu của constructor và những URL được `addURL` bổ sung sau này.
- **`addURL(URL)`** nối một URL vào cuối danh sách đường tìm của **instance ấy**. Nó **không** tạo object `Class<?>` ngay, không nạp trước toàn bộ JAR và không mở rộng application classpath của cả JVM.
- `addURL` là **`protected`**, nên mã Java bên ngoài lớp/subclass theo quy tắc truy cập của Java không được gọi trực tiếp như một public API. Nếu ứng dụng thực sự sở hữu custom loader, subclass có thể cung cấp một wrapper được kiểm soát.

Hai hiểu lầm cần tránh ngay:

1. `getURLs()` **không phải API liệt kê toàn bộ classpath/module path hoặc mọi vị trí class có thể được tìm thấy trong JVM**.
2. `addURL` **không phải cơ chế sửa class đã được định nghĩa**, không thể bắt JVM nạp lại một tên đã có trên cùng defining loader.

Ví dụ `loader.getURLs()` trả 2 URL không có nghĩa loader đã tải 2 class, có đúng 2 JAR, hay hai nguồn này là tất cả những nguồn do parent và modules cung cấp.

## 2. Cách cấu tạo URLClassLoader và thứ tự tìm kiếm

Một cách tạo loader:

```java
import java.net.URL;
import java.net.URLClassLoader;

URL[] paths = { firstUrl, secondUrl };
ClassLoader parent = ClassLoader.getPlatformClassLoader();

try (URLClassLoader loader = new URLClassLoader(paths, parent)) {
    // loader tìm lớp/resource ở các URL được cung cấp,
    // sau khi delegation đến parent theo hành vi mặc định.
}
```

Đoạn trên **là snippet**: `firstUrl`, `secondUrl` cần được khai báo trước. Nó minh họa kiểu constructor và parent.

Trong cách sử dụng mặc định của `URLClassLoader`:

```text
loadClass("com.example.Widget")
           |
           v
      findLoadedClass(...)
           |
       đã có? ----- yes ----> trả Class<?> đã được ghi nhận
           |
           no
           v
     delegate tới parent
           |
      tìm được? ---- yes ----> trả Class<?> do parent nạp/định nghĩa
           |
           no
           v
      URLClassLoader.findClass(...)
           |
           +--> duyệt các URL đường tìm theo thứ tự phù hợp
           '--> tìm entry com/example/Widget.class
                      |
                      '--> định nghĩa class trong loader này
```

Đây là luồng tổng quát của `ClassLoader.loadClass` mặc định cùng `URLClassLoader.findClass`; custom loader có thể điều chỉnh cách delegation. `URLClassLoader` tra cứu URL theo thứ tự được khai báo, **sau khi parent đã được thử trước**, nếu không có lớp đã được ghi nhận.

Kết quả quan trọng: nếu parent đã tìm được `com.example.Widget`, việc thêm một JAR khác cũng chứa `com.example.Widget` vào child **không khiến child override class của parent** trong chính sách parent-first bình thường.

## 3. getURLs() thực sự cho biết những gì?

Theo Java SE API, `URLClassLoader.getURLs()` trả các URL dùng làm search path cho class/resource của loader đó. Mảng được trả về chứa:

- Những URL được đưa vào **constructor** khi tạo instance.
- Những URL được **thực sự append** bằng `addURL`, theo thứ tự trong đường tìm.
- Không phải các lớp đã nạp, không phải mọi tài nguyên từng sử dụng.

Với:

```java
URLClassLoader loader = new URLClassLoader(
        new URL[] {urlA, urlB}, parent);
```

`loader.getURLs()` sẽ thể hiện danh sách bắt đầu bằng `urlA`, `urlB`. Khi subclass gọi `addURL(urlC)` thành công, `getURLs()` sẽ phản ánh URL mới ở phía sau.

**Không suy diễn được các dữ liệu sau chỉ từ `getURLs()`:**

| Muốn biết | `getURLs()` có đủ không? | Vì sao |
| --- | --- | --- |
| Đường tìm được cấu hình trực tiếp cho **loader này** | Có, trong phạm vi API. | Đây là hợp đồng của method. |
| JAR nào chắc chắn chứa một class cụ thể | Không. | URL có thể trỏ nguồn không có class đó hoặc chưa mở, JAR có nhiều entries. |
| Class đã từng được định nghĩa bởi loader | Không. | `getURLs` là cấu hình đường tìm, không phải history log. |
| Class nào đang được parent cung cấp | Không. | Parent có nguồn và chiến lược lookup riêng. |
| Tất cả classpath và module path của toàn JVM | Không. | Có bootstrap/platform/system loaders, modules và custom loaders khác. |
| Thứ tự thực sự chọn một class trùng tên trong mọi tình huống | Không. | Cần xét delegation, thứ tự URL, nguồn phụ và tình trạng đã load. |
| Các resource hiện đang mở/đã đóng | Không. | URL cấu hình khác file descriptors/stream state. |
| Classpath mà `java` khởi chạy nhận từ `-cp` | Không nhất thiết. | Một custom URLClassLoader có thể hoàn toàn tách biệt application loader. |

Đừng sửa phần tử của mảng kết quả rồi kỳ vọng đổi cấu hình loader. `getURLs()` là **phương thức quan sát**; API thay đổi đường tìm (nếu có quyền) là `addURL`. Muốn ứng dụng dễ kiểm soát, hãy lưu nguồn cấu hình riêng thay vì lấy mảng URL rồi sử dụng như nơi lưu trạng thái có thể sửa.

### URL trong getURLs có thể chưa được mở

Có URL trong đường tìm không phải bằng chứng tệp tồn tại, có thể truy cập được hoặc đã được mở thành JAR. Việc thực sự tải class/resource mới là hành động làm implementation cần truy cập nguồn. Nếu URL sai, thiếu quyền, archive hỏng, hoặc file không có entry tương ứng, lookup vẫn có thể thất bại.

## 4. addURL là protected: đúng phạm vi truy cập

Javadoc định nghĩa:

```java
protected void addURL(URL url)
```

Vì vậy đoạn code sau **không compile được** từ một class không có quyền `protected` thích hợp:

```java
URLClassLoader loader = new URLClassLoader(new URL[0]);
loader.addURL(newUrl); // addURL(URL) has protected access
```

Đây là **snippet cố ý sai để minh họa compile error**; `newUrl` phải được khai báo nếu thử riêng. Sai lầm là nghĩ “method xuất hiện trong Javadoc nên caller nào cũng gọi được”.

Cách hợp lệ khi thật sự muốn bổ sung nguồn vào loader riêng:

```java
import java.net.URL;
import java.net.URLClassLoader;

public final class ExtensibleLoader extends URLClassLoader {
    public ExtensibleLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    public void append(URL url) {
        super.addURL(url);
    }
}
```

Đây là **một class Java biên dịch độc lập** nếu lưu tên `ExtensibleLoader.java`; nó không có `main`, dùng làm component trong ứng dụng.

Đừng dùng reflection lên `URLClassLoader.addURL` hoặc JDK internal loaders để né `protected` trong sản phẩm. Java 9+ áp dụng module encapsulation mạnh hơn, và cách đó còn phụ thuộc kiểu implementation của loader thực.

### Vì sao wrapper cần được thiết kế cẩn thận?

Wrapper public `append` có thể khiến bất kỳ caller có reference tới loader đó thêm dependency không mong muốn. Trong hệ plugin thật, chỉ cấp API này cho mã quản lý plugin, kiểm tra URL/path được cho phép, ownership của loader, chính sách resource/certificates, trạng thái close và concurrency.

Một wrapper tối giản dùng trong demo cho thấy **cơ chế API**; không tự tạo chính sách an toàn hay quản lý vòng đời hoàn chỉnh.

## 5. addURL nối URL như thế nào? null, trùng và loader đã đóng

Theo API Java SE 21:

| Trường hợp | Kết quả với `addURL` |
| --- | --- |
| URL hợp lệ, chưa có, loader chưa đóng | URL được nối vào cuối search path. |
| `url == null` | Không có tác dụng. |
| URL đã tồn tại trong danh sách | Không có tác dụng; không append bản trùng. |
| Loader đã bị `close()` | Không có tác dụng. |

Ví dụ một loader có thứ tự ban đầu `[A, B]`:

```text
getURLs()         -> [A, B]
addURL(C)         -> [A, B, C]
addURL(C)         -> [A, B, C]   (không trùng)
addURL(null)      -> [A, B, C]   (không thay đổi)
close()
addURL(D)         -> [A, B, C]   (đã đóng, không thêm)
```

Đây là sơ đồ khái niệm theo contract; `A`, `B`, `C`, `D` là URL, không phải code Java. Kiểm tra URL “đã có trong danh sách” dựa vào semantics so sánh URL mà implementation sử dụng; đừng dùng giả định mọi spelling tương đương của một path đều được chuẩn hóa giống nhau. Hãy đưa vào path/URL đã chuẩn hóa rõ ràng để tránh các nguồn trùng ngữ nghĩa khó phát hiện.

**Nối URL không xác nhận JAR đã hợp lệ.** Phần tử vừa append có thể trỏ tới file bị xóa, archive không chứa entry cần tìm hoặc dữ liệu không phải class file; lỗi sẽ xuất hiện khi cần tra cứu.

## 6. Thực hành chạy được: trước và sau khi addURL

Ví dụ dùng **hai thư mục chứa class** tách khỏi application classpath. Ta chạy ứng dụng từ `build/app`, chủ động cho custom loader nhìn thấy `build/first`, sau đó mới append `build/second`.

### Cấu trúc project

```text
src/
  first/
    example/
      First.java
  second/
    extra/
      Second.java
  app/
    UrlPathsDemo.java
build/
  first/           (javac tạo)
  second/          (javac tạo)
  app/             (javac tạo)
```

**File `src/first/example/First.java`:**

```java
package example;

public class First {
    public String value() {
        return "first";
    }
}
```

**File `src/second/extra/Second.java`:**

```java
package extra;

public class Second {
    public String value() {
        return "second";
    }
}
```

**File `src/app/UrlPathsDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class UrlPathsDemo {
    static final class MutableLoader extends URLClassLoader {
        MutableLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        public void append(URL url) {
            super.addURL(url);
        }
    }

    public static void main(String[] args) throws Exception {
        URL first = Path.of("build/first")
                .toAbsolutePath().toUri().toURL();
        URL second = Path.of("build/second")
                .toAbsolutePath().toUri().toURL();

        Class<?> saved;

        try (MutableLoader loader = new MutableLoader(
                new URL[]{first}, ClassLoader.getPlatformClassLoader())) {

            System.out.println("initial URLs: " + loader.getURLs().length);

            System.out.println("first defined here: "
                    + (loader.loadClass("example.First")
                            .getClassLoader() == loader));

            System.out.println("parent class visible: "
                    + (loader.loadClass("java.lang.String") == String.class));

            try {
                loader.loadClass("extra.Second");
                System.out.println("unexpected second load");
            } catch (ClassNotFoundException expected) {
                System.out.println("second before append: missing");
            }

            loader.append(second);

            System.out.println("after append URLs: "
                    + loader.getURLs().length);

            System.out.println("second appended last: "
                    + loader.getURLs()[1].equals(second));

            loader.append(second);
            loader.append(null);

            System.out.println("duplicate and null ignored: "
                    + (loader.getURLs().length == 2));

            saved = loader.loadClass("extra.Second");

            System.out.println("second defined here: "
                    + (saved.getClassLoader() == loader));
        }

        System.out.println("loaded class usable after close: "
                + saved.getMethod("value")
                        .invoke(saved.getConstructor().newInstance()));
    }
}
```

### Biên dịch và chạy

Chạy các lệnh từ thư mục gốc có `src` (lệnh shell không phụ thuộc `CLASSPATH` global):

```bash
javac -d build/first src/first/example/First.java
javac -d build/second src/second/extra/Second.java
javac -d build/app src/app/UrlPathsDemo.java
java -cp build/app UrlPathsDemo
```

**Stdout đã biên dịch và đối chiếu trên JDK 24; code chỉ dùng API có trong Java 17+:**

```text
initial URLs: 1
first defined here: true
parent class visible: true
second before append: missing
after append URLs: 2
second appended last: true
duplicate and null ignored: true
second defined here: true
loaded class usable after close: second
```

### Điều gì được chứng minh?

1. URL đầu tiên trỏ tới `build/first` nên custom loader tự định nghĩa `example.First`.
2. Mặc dù `getURLs()` chỉ có **một URL**, loader vẫn tìm `java.lang.String` qua parent delegation. Do đó **không được coi `getURLs()` là toàn bộ không gian tìm class**.
3. `extra.Second` chưa có trong đường tìm, lần `loadClass` đầu ném `ClassNotFoundException` và được catch có chủ đích.
4. Sau `append(second)`, mảng `getURLs()` dài 2 và URL mới đứng cuối. Lần `loadClass("extra.Second")` trực tiếp sau đó thành công. Đây là bằng chứng rằng **nguồn mới có thể dùng cho lần tìm class tiếp theo** trong cấu hình demo.
5. Thêm lại URL trùng và thêm `null` không làm tăng số phần tử.
6. Sau khi đóng loader, **class đã được định nghĩa** có thể tiếp tục được sử dụng thông qua `Class<?>`, object và metadata còn sống. `close()` không phải lệnh “xóa class khỏi JVM”.

Đừng suy diễn từ dòng 4 rằng **mọi** `NoClassDefFoundError` trong bytecode hoặc mọi kết quả resolution thất bại trước đó sẽ tự sửa sau khi append URL. `ClassNotFoundException` trong ví dụ phát sinh từ **lời gọi trực tiếp `loader.loadClass`**; JVM còn có semantics caching/linking của symbolic references. Với môi trường runtime plugin, tránh thiết kế phụ thuộc việc vá classpath sau khi một phần dependency đã linking thất bại.

### Biến thể nạp từ JAR

Trong ví dụ, đường `build/second` là directory URL. Nếu muốn nạp từ JAR, sau khi compile class thứ hai:

```bash
jar --create --file second.jar -C build/second .
```

Thay phần khai báo `second` trong `UrlPathsDemo.java` bằng:

```java
URL second = Path.of("second.jar")
        .toAbsolutePath().toUri().toURL();
```

Sau khi biên dịch lại `UrlPathsDemo` và chạy với `java -cp build/app UrlPathsDemo`, custom loader sẽ tìm `extra/Second.class` trong `second.jar`. Đây là **biến thể của chương trình**, không copy thêm một khai báo biến `second` vào cùng scope.

`Path.toUri().toURL()` cho directory cần mang dấu `/` cuối, phù hợp với contract `URLClassLoader`. Một `file:` URL chỉ tới JAR thì không kết thúc bằng `/`; nếu tự ghép URL bằng string dễ dẫn đến hiểu lầm directory và archive. Dùng `Path.toUri().toURL()` thay vì nối `"file:" + path` để xử lý khoảng trắng và ký tự đặc biệt.

## 7. Những giới hạn quan trọng của addURL

### 7.1. Chỉ thay đường tìm của loader mà nó được gọi

`append` gọi `addURL` của **một instance URLClassLoader**. Nó không:

- Thay `System.getProperty("java.class.path")` theo contract.
- Thay đường tìm class của bootstrap/platform/system loaders.
- Thay configuration của các URLClassLoader khác.
- Bắt các class loader khác sử dụng URL vừa thêm.
- Thêm module mới vào named module graph hay module layer tự động.

Nếu host framework dùng một loader khác để tìm plugin, append URL vào loader tự tạo nhưng **không đưa loader ấy vào đường đi nạp class** sẽ không có ích. Phải gọi `loader.loadClass(...)` hoặc API plugin phù hợp.

### 7.2. Không thể thay thế một class đã được định nghĩa

JVM định danh một class/interface thông thường bằng **(binary name, defining class loader)**. Nếu loader đã định nghĩa `com.example.Plugin` từ `v1.jar` thì thêm `v2.jar` chứa cùng binary name không làm loader nạp lại `v2` với tên đó.

Ví dụ:

```text
URL loader path = [v1.jar]
loadClass("com.example.Plugin") -> Class object P1

addURL(v2.jar)
loadClass("com.example.Plugin") -> vẫn dùng Class P1
```

Phải phân biệt **tái yêu cầu cùng tên trên cùng loader** với **tạo một loader mới** (có thể định nghĩa class khác cùng tên). Loader mới cho ra **một runtime type khác**, gây vấn đề `ClassCastException` nếu host và plugin có hai bản API/interface. Thiết kế plugin nên đặt API chung trên parent loader thích hợp, chỉ định nghĩa implementation trong loader riêng.

### 7.3. Parent delegation có thể thắng URL mới

Nếu parent đã định nghĩa `com.acme.Config`, việc thêm `override.jar` chứa `com/acme/Config.class` vào child không thay được class do parent trả về trong parent-first search mặc định.

Cũng cần phân biệt **ClassLoader.loadClass** và **findClass**. `URLClassLoader.findClass` chỉ tìm class trong URL path của loader; `loadClass` còn xét lớp đã load và parent delegation. Không tự gọi `findClass` để qua mặt parent nếu không có lý do kiến trúc rõ ràng.

### 7.4. URL mới không đồng nghĩa dependency graph đầy đủ

Một JAR có thể tham chiếu classes trong các JAR khác. Thêm URL của `plugin.jar` giúp loader thấy bytecode của plugin, **không tự đảm bảo** đủ transitive dependencies. Nếu method/field/class liên quan thiếu khi link hoặc run, vẫn có thể gặp `NoClassDefFoundError`, `NoSuchMethodError`, `VerifyError` hoặc `ClassNotFoundException` tùy đường đi.

Không có đảm bảo một JAR có thể được dùng như plugin “an toàn” chỉ vì `getURLs()` trả về tên của nó. Package sealing, version conflict, code source, resource collisions và module access vẫn phải được xét.

### 7.5. getURLs() không phản ánh parent, manifest và module graph như inventory

Một URLClassLoader có thể truy cập class `java.lang.String` qua parent nhưng `getURLs()` không bao gồm các lớp nền tảng ấy. Một JAR có `Class-Path` trong manifest còn có thể khiến việc tìm class/resource liên quan tới các vị trí mà **không phải mọi nơi đều được thể hiện như một URL được append trực tiếp**. Vì vậy hãy hiểu `getURLs()` là **đường tìm URL được cấu hình của instance**, không phải một biểu diễn chuẩn của toàn bộ dependency graph hay các nguồn transitive.

### 7.6. Không dùng getURLs() để ép system loader thành URLClassLoader

Đoạn code cũ:

```java
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
URL[] urls = app.getURLs();
```

Có thể từng chạy trên một số JDK 8 mặc định, nhưng **không di động**: từ JDK 9, built-in application class loader của Oracle/OpenJDK không còn là `URLClassLoader`. Phép ép kiểu có thể ném `ClassCastException`. `ClassLoader.getSystemClassLoader()` khai báo trả về `ClassLoader`, không hứa kiểu concrete nào.

Nếu mục đích là chẩn đoán classpath khởi động, dùng cấu hình launcher/build, `System.getProperty("java.class.path")` cùng thông tin môi trường (và lưu ý property ấy không chứa mọi custom loader/modules). Nếu mục đích là mở rộng plugin source, **tạo và quản lý URLClassLoader riêng** thay vì mutate system loader.

## 8. Close() có ý nghĩa gì đối với getURLs và addURL?

`URLClassLoader` triển khai `Closeable`/`AutoCloseable`; method `close()` được thêm từ Java 7, nên phù hợp với `try-with-resources`.

Khi đóng:

- Loader không còn được dùng để **nạp class/resource mới do chính nó định nghĩa/tìm**.
- Class/resource do parent cung cấp vẫn có thể truy cập theo delegation.
- Class/object đã load trước khi đóng vẫn có thể tồn tại và tiếp tục sử dụng.
- Với URL `jar:` và `file:`, loader cố đóng các file do chính nó mở; `close()` có thể ném `IOException`, lỗi bổ sung có thể ở suppressed exceptions.
- Gọi `close()` thêm lần nữa không có tác dụng; `addURL` sau close cũng **không có tác dụng**.
- Nếu một thread đang load class trong lúc thread khác gọi `close()`, Javadoc nêu kết quả của lần load ấy là **không xác định**.

Ví dụ điều nên tránh:

```java
URLClassLoader loader = new URLClassLoader(urls, parent);
// Thread A: loader.loadClass(...)
// Thread B: loader.addURL(...), loader.close(), loader.addURL(...)
// Không thiết kế dựa trên tương tác concurrent thiếu đồng bộ và lifecycle rule.
```

Đoạn trên chỉ là pseudo-code kiến trúc, không phải chương trình độc lập. Hãy quản lý đồng bộ, quyền sở hữu và trạng thái loader ở tầng ứng dụng. Với plugin manager, thường dùng một loader theo thế hệ plugin, ngăn thao tác tải mới trước khi đóng và giải phóng các tham chiếu khi có thể.

**Đóng loader không buộc JVM unload class ngay.** JVM chỉ có thể thu hồi khi loader và các metadata/object liên quan đủ điều kiện GC; các thread, static caches, TCCL và callbacks có thể giữ reference.

**Đọc `getURLs()` sau close không chứng minh loader còn dùng được.** Nó mô tả cấu hình đã có; để xác định lifecycle phải theo dõi trạng thái bạn tự quản lý và kết quả các API, không dựa vào việc mảng URL vẫn xuất hiện.

## 9. Thực hành lựa chọn giải pháp đúng theo mục đích

| Nhu cầu | Lựa chọn nên dùng | Tránh |
| --- | --- | --- |
| Liệt kê URL được cấu hình trên **một URLClassLoader có thật** | `thatUrlLoader.getURLs()` | Giả định đó là toàn bộ Java classpath. |
| Tải class từ JAR/directory mới với loader riêng | Tạo `URLClassLoader(urls, parent)` hoặc subclass expose `append` có kiểm soát | Ép application loader sang `URLClassLoader`. |
| Tìm class đã có trong môi trường ứng dụng | `Class.forName` hoặc `ClassLoader.loadClass` với đúng loader | Thêm URL mới nếu chẳng liên quan nguồn thiếu. |
| Đọc resource trong JAR | `Class.getResourceAsStream`/`ClassLoader.getResourceAsStream` | Suy từ `getURLs` rồi tự biến mọi URL thành `File`. |
| Dò nhiều resource trùng tên | `getResources` theo loader thật | Tin rằng `getURLs` xác định hết thứ tự resource. |
| Tải các provider theo SPI | `ServiceLoader` cùng parent/loader/module phù hợp | Đoán class tên nào có trong mọi JAR qua mảng URL. |
| Thêm dependency cố định lúc khởi động | Cấu hình `-cp` hoặc module path trong launcher/build tool | Gọi `addURL` giữa lúc process đã run mà không kiểm soát trạng thái. |
| Hot reload plugin / đổi version | Thiết kế loader mới theo thế hệ, quản lý API chung và lifecycle | Append JAR mới rồi trông đợi class đã nạp tự được thay. |
| Tìm nguồn của một class cụ thể | Quan sát `clazz.getClassLoader()`, code source khi có, debug class loading | Coi `getURLs()[0]` chắc chắn chứa class ấy. |

Một loader riêng có parent = `ClassLoader.getPlatformClassLoader()` như demo thường dùng tốt cho plugin không phụ thuộc các interface riêng của host. Nếu plugin cần implement interface của host, parent nên là loader **nhìn thấy cùng định nghĩa host API**, nếu không có thể xảy ra bất tương thích kiểu dù binary name giống nhau.

## 10. Cách debug khi addURL không cho kết quả mong muốn

Trường hợp `append(pluginUrl)` xong vẫn gặp `ClassNotFoundException`:

1. **Xác nhận instance:** mã đang gọi `loadClass` trên **đúng loader đã append** chưa? Có phải framework đang dùng TCCL/system/child khác?
2. **Xem `getURLs()`:** URL đã nằm ở cuối path chưa? Nếu không, kiểm tra `null`, duplicate, trạng thái đã close hoặc wrapper có thực sự gọi `super.addURL`.
3. **Kiểm tra URL scheme:** directory URL nên kết thúc bằng `/`, JAR path nên trỏ file JAR. Dùng `Path.toAbsolutePath().toUri().toURL()` để tránh lỗi escape đường dẫn.
4. **Kiểm tra file/entry:** `jar tf plugin.jar` có đúng `com/acme/Plugin.class` không? Binary name đưa `loadClass` phải là `com.acme.Plugin`, không phải `com/acme/Plugin.class`.
5. **Kiểm tra parent delegation:** parent có định nghĩa trước một class cùng tên hoặc chưa? Nếu có thì child có thể không đọc entry mới.
6. **Kiểm tra dependency transitively:** JAR plugin có class đích nhưng thiếu các API/base class/interface cần cho verifier/linking không?
7. **Đọc exception đầy đủ:** `ClassNotFoundException` khác `NoClassDefFoundError`, `ClassFormatError`, `LinkageError` hoặc `ClassCastException`. Không gộp mọi lỗi nạp/lần gọi thành “addURL không hoạt động”.
8. **Xác minh lifecycle:** loader có bị `close()` hay thay bằng instance khác? Có thread còn giữ loader cũ không?
9. **Không dựa trên thứ tự ngẫu nhiên:** nếu hai URL chứa trùng class/resource, chọn thứ tự tường minh và tránh duplicate dependencies.
10. **Không lấy `getURLs` làm chứng minh cuối:** cần quan sát `Class<?> clazz` của kết quả thực, `clazz.getClassLoader()`, resource URLs và nguồn deployment khi thích hợp.

Cách quan sát tài nguyên của loader được điều khiển:

```java
// Snippet trong method có một URLClassLoader named loader:
URL[] configured = loader.getURLs();
for (URL url : configured) {
    System.out.println("configured: " + url);
}

var found = loader.getResource("com/acme/config.properties");
System.out.println("found: " + found);
```

`found` có thể đến từ parent hoặc URL của loader theo quy tắc tìm tài nguyên. Đừng dùng đường dẫn in ra để suy diễn không có security/encapsulation issues; trong named modules một số resources còn chịu module access rules.

HotSpot có logging `-Xlog:class+load=info` để xem nguồn tải class:

```bash
java -Xlog:class+load=info -cp build/app UrlPathsDemo
```

Lệnh này in thêm nhiều dòng JVM nên **không dùng làm chuẩn stdout của thí nghiệm mục 6**. Class loading log không phải một bản ghi đầy đủ tất cả lookup URL/resource.

## 11. Lỗi phổ biến và cách sửa

| Lỗi hoặc giả định | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `URLClassLoader addURL` được gọi trực tiếp từ class bất kỳ | `addURL` là `protected`. | Subclass tạo wrapper có quyền và kiểm soát nguồn. |
| Sau append, `getURLs()` tăng nên mọi class trong JAR đã load | API chỉ thay search path. | Chỉ load class khi cần; kiểm tra `Class<?>` thực trả về. |
| `getURLs()` trả 1 URL nên loader chỉ thấy 1 nguồn | Parent delegation vẫn có thể cung cấp classes. | Phân tích cả parent và loader graph. |
| Thêm URL trùng hai lần để đổi priority | `addURL` bỏ qua URL trùng. | Tạo loader mới với thứ tự path mong muốn. |
| Append `null` sẽ tạo entry placeholder | API bỏ qua `null`. | Kiểm tra/validate cấu hình đầu vào. |
| Thêm v2.jar sẽ cập nhật class v1 đã nạp | Class identity gắn với defining loader và binary name. | Tạo loader mới cho thế hệ plugin, quản lý API chung. |
| Cast system loader sang URLClassLoader để addURL | JDK 9+ built-in app loader không phải URLClassLoader. | Dùng own loader, classpath launch-time hoặc đúng framework API. |
| Sau close append vẫn dùng được | `addURL` sau close không có tác dụng. | Tạo loader mới hoặc giữ loader mở đúng vòng đời. |
| URL directory thiếu dấu `/` cuối | URLClassLoader có thể hiểu sai loại nguồn. | Dùng `Path.toUri().toURL()`, kiểm tra URL. |
| `getURLs` hiển thị URL nhưng `findClass` không thấy class | URL có thể hỏng, thiếu entry hoặc quyền truy cập. | Kiểm tra tệp, archive và class-file path. |
| Parent có class cùng tên nhưng muốn plugin override | Parent-first chọn parent trước. | Thiết kế package/loader isolation có chủ đích; tránh override tùy tiện. |
| Gọi close đồng thời với loadClass | Javadoc quy định kết quả của lần load đang diễn ra là không xác định. | Đồng bộ lifecycle của plugin loader. |

## 12. Câu hỏi ôn tập có đáp án

1. **`getURLs()` có liệt kê JDK bootstrap/platform module classes không?**  
   Không. Nó trả search URLs được cấu hình cho chính URLClassLoader, còn parent/modules hoạt động riêng.
2. **`addURL` là public method?**  
   Không, nó là `protected`. Từ một subclass được phép, dùng `super.addURL(url)`, hoặc tạo loader mới với constructor URLs.
3. **`addURL(null)` làm gì?**  
   Không có tác dụng theo Javadoc.
4. **Append lại URL đã tồn tại có làm tăng `getURLs().length`?**  
   Không; URL trùng bị bỏ qua.
5. **Trong loader mặc định parent-first, nếu parent đã load class `p.X` thì append JAR chứa `p.X` vào child có thay được không?**  
   Không; lookup sẽ tiếp tục có thể trả class do parent định nghĩa.
6. **Thêm JAR vào loader có lập tức initialize mọi class trong đó không?**  
   Không; nó chỉ mở rộng nguồn tìm, không gọi constructors/static initializers.
7. **Vì sao `ClassNotFoundException` trước append trong demo được giải quyết sau append?**  
   Vì lời gọi `loader.loadClass` trực tiếp sau đó dùng đường tìm mở rộng và tìm thấy class chưa được định nghĩa trước đó.
8. **Có thể dựa vào việc append để chữa mọi `NoClassDefFoundError` đã xảy ra lúc linking?**  
   Không. Resolution/loading có semantics riêng; cần thiết kế initialization và dependency loading nhất quán.
9. **`close()` có làm mất Class<?> đã được định nghĩa?**  
   Không. Các class đã load vẫn có thể tiếp tục được dùng; close chủ yếu hạn chế load mới và đóng tài nguyên mở.
10. **Khi plugin cần interface của host, parent nên chọn gì?**  
    Loader có thể cung cấp cùng định nghĩa host API/interface; không tự động chọn platform loader nếu plugin cần host types.
11. **Sửa phần tử trong mảng `getURLs()` có phải cách append chính thức?**  
    Không. `getURLs` dùng để xem đường tìm; append là method riêng `addURL` theo quyền truy cập và lifecycle.
12. **Nếu `getURLs()` có ba URL nhưng ClassLoader.loadClass tìm được class từ parent, class defining loader là ai?**  
    Parent (nếu parent trực tiếp define class), không nhất thiết URLClassLoader chứa ba URL.

## 13. Nguồn tham khảo chuẩn

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `getURLs`, `addURL`, `findClass`, constructors, `close` và giới hạn khi loader đóng.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, parent delegation và type identity.
- [Java SE 21 — URL](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URL.html): URL protocol, equality và cú pháp đường dẫn.
- [Java SE 21 — Path.toUri](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toUri()): chuyển directory/JAR path thành URI đúng định dạng.
- [Java SE 21 — JarFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): cơ chế archive khi cần đọc/kiểm tra entries.
- [JVM Specification `5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): binary name và defining class loader.
- [Oracle JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): thay đổi built-in application loader; không còn subtype URLClassLoader.
