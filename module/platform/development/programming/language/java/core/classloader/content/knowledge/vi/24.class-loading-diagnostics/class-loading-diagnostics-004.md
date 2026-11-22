# Liệt kê tài nguyên trùng tên và xác định thứ tự được chọn

## 1. Vì sao cấu hình đúng vẫn đọc ra dữ liệu sai?

Trong một ứng dụng Java có nhiều JAR, những file dưới cùng resource path có thể tồn tại đồng thời, ví dụ `config/settings.properties`, `log4j2.xml`, `META-INF/services/com.example.Service` hoặc `sample/diagnostics/order.txt`. Host, plugin và hai phiên bản dependency có thể mang **những bản khác nhau với cùng một tên tài nguyên**.

Nếu code chỉ gọi:

~~~java
URL selected = loader.getResource("config/settings.properties");
~~~

thì nó nhận **một URL** hoặc `null`. Việc này **không có nghĩa chỉ một file tồn tại trên classpath**. Loader có thể đã chọn resource của parent trước file thuộc plugin.

Muốn biết có bao nhiêu ứng viên, dùng:

~~~java
Enumeration<URL> candidates =
        loader.getResources("config/settings.properties");
while (candidates.hasMoreElements()) {
    System.out.println(candidates.nextElement());
}
~~~

**Phân biệt bốn câu hỏi:**

1. `getResource(name)` — resource **đầu tiên được chọn** là URL nào?
2. `getResources(name)` — **mọi resource cùng tên** mà loader nhìn thấy, với thứ tự enumeration, là những URL nào?
3. `findResource(name)` và `findResources(name)` — loader tìm được gì **trong chính nguồn của mình** khi không thêm bước tra cứu parent mặc định?
4. `getResourceAsStream(name)` — bytes thực tế được đọc từ **resource được chọn** là gì?

Bài thuộc nhóm **Chẩn đoán**, trình bày logic resource lookup của ClassLoader, cách phân biệt parent-first với child-local search, cách xác định JAR nào đang thắng, giới hạn module/resource encapsulation, `ServiceLoader` và các chiến lược xử lý duplicate resources. Ví dụ Java 17+ được biên dịch, đóng JAR và chạy thật với 12 dòng stdout kiểm chứng.

## 2. Resource path, URL và classpath root

### 2.1. Resource name không phải filesystem path

Tên resource dùng dấu `/` và được hiểu tương đối với một classpath/resource root:

~~~text
sample/diagnostics/order.txt
META-INF/services/com.example.spi.Processor
com/example/defaults.json
~~~

Cùng tên `sample/diagnostics/order.txt` có thể có những vị trí vật lý khác nhau:

~~~text
file:/app/classes/sample/diagnostics/order.txt
jar:file:/app/lib/a.jar!/sample/diagnostics/order.txt
jar:file:/app/lib/b.jar!/sample/diagnostics/order.txt
~~~

Các đường trên chỉ minh họa URL. `jar:file:...!/` là dạng URL chỉ một entry trong JAR; dấu `!/` không thuộc tên resource logic mà caller truyền cho `getResource`.

Resource cũng có thể xuất hiện thông qua custom loader, nested-JAR-aware launcher hoặc module runtime image, không nhất thiết có `Path` file bình thường.

### 2.2. Trùng tên không đồng nghĩa trùng bytes

Hai URL khác nhau có thể chứa hai phiên bản cấu hình khác nhau, hoặc hai bản có nội dung giống hệt. Muốn biết, hãy **đọc bytes** hay tính checksum. Chỉ so URL strings không đủ kết luận hai streams giống nhau.

Trong một hệ plugin:

~~~text
Application ClassLoader
  sample/diagnostics/order.txt = HOST

Child URLClassLoader
  URL #1 a.jar
    sample/diagnostics/order.txt = JAR_A
  URL #2 b.jar
    sample/diagnostics/order.txt = JAR_B
~~~

Việc có ba bản cùng tên không phải lỗi định dạng JAR. Quy tắc **lựa chọn một bản**, **đọc tất cả** hoặc **merge** thuộc API và framework đang tiêu thụ resource.

### 2.3. Trùng resource không phải duplicate class definition

Nhiều JAR cùng có `config/app.properties` hoàn toàn có thể hợp lệ. Nhưng nếu hai JAR cùng có `com/example/Foo.class`, chương trình còn có câu hỏi về class identity và nguồn code thực sự đã được định nghĩa.

`ClassLoader.getResources("com/example/Foo.class")` có thể là một tín hiệu chẩn đoán để tìm class files trùng, nhưng **không bảo đảm chính URL đó là bytes đã tạo `Class<?>` đang chạy**: loaders có thể transform bytecode, dùng memory buffers, class caches hoặc custom module lookup. Khi debug class, kết hợp `clazz.getClassLoader()`, `clazz.getModule()` và provenance phù hợp.

## 3. Các API liệt kê và chọn resource

### 3.1. `ClassLoader.getResource(String)`

~~~java
URL url = loader.getResource("sample/diagnostics/order.txt");
if (url == null) {
    System.out.println("not found");
} else {
    System.out.println(url);
}
~~~

Đây là đoạn mã minh họa dùng biến `loader` trong method. Theo Javadoc Java SE 21, implementation mặc định tìm **parent loader trước**; nếu parent `null` thì tìm đường của bootstrap/VM built-in loader; sau khi parent không thấy mới gọi `findResource` của current loader.

Do đó, một resource ở parent có thể **che** resource cùng tên ở child khi gọi API chọn một bản.

### 3.2. `ClassLoader.getResources(String)`

~~~java
Enumeration<URL> found = loader.getResources(
        "sample/diagnostics/order.txt");
while (found.hasMoreElements()) {
    URL candidate = found.nextElement();
    System.out.println(candidate);
}
~~~

Method này khai báo `throws IOException`. **Khi không có file nào**, nó trả `Enumeration<URL>` **rỗng**, không phải `null`.

Implementation mặc định duyệt **toàn bộ URL ở parent** trước, rồi ghép **toàn bộ URL của `findResources` tại loader hiện tại**. Đây là khác biệt chính so với `getResource`: bạn nhìn thấy cả các bản thua trong cuộc chọn.

Javadoc khuyến nghị custom loaders bảo đảm `getResources`/`getResource` nhất quán, để phần tử đầu tiên của enumeration tương ứng URL `getResource` trả về. Khi loader override hai phương thức bằng chiến lược riêng, **phải kiểm chứng** điều đó thay vì xem như quy luật áp dụng cho mọi custom loader.

### 3.3. `ClassLoader.resources(String)` — dạng Stream từ Java 9

~~~java
try (java.util.stream.Stream<URL> stream =
        loader.resources("sample/diagnostics/order.txt")) {
    stream.forEach(System.out::println);
}
~~~

Đây là snippet Java 17 trong method; implementation mặc định tạo Stream từ `getResources`. Nó không phải `Files.walk` và không tự liệt kê mọi file trên classpath, mà chỉ tìm **cùng tên đã truyền**.

### 3.4. `ClassLoader.getResourceAsStream(String)`

~~~java
try (InputStream in =
        loader.getResourceAsStream("sample/diagnostics/order.txt")) {
    if (in == null) {
        System.out.println("not found");
    } else {
        System.out.println(in.readAllBytes().length);
    }
}
~~~

Snippet cần `java.io.InputStream` và xử lý IOException. Method này đọc **một bản được chọn** theo search order tương đương `getResource`, không liệt kê duplicates. Nếu muốn kiểm tra nội dung **từng bản**, duyệt `getResources` và mở `URL.openStream()` trong `try-with-resources`.

### 3.5. `findResource` và `findResources`

Đây là protected hooks mà subclasses như `URLClassLoader` triển khai cho việc tìm resource trong nguồn **riêng**:

~~~java
final class InspectableLoader extends URLClassLoader {
    InspectableLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    URL localFirst(String name) {
        return findResource(name);
    }

    Enumeration<URL> localAll(String name) throws IOException {
        return findResources(name);
    }
}
~~~

Đây là một **snippet class**, cần imports đầy đủ. Nó không đổi policy resource lookup: chỉ expose hai hooks để so sánh với `getResource` và `getResources`.

**Quan trọng:** `findResources` không có nghĩa “`getResources` nhưng không trả duplicates”. Nó chỉ không tự thêm bước tìm parent của phương thức mặc định. Nó vẫn có thể trả nhiều URLs nếu child có nhiều URL roots cùng tên.

### 3.6. Bảng tổng hợp

| API | Trả kết quả | Thứ tự/tập tìm theo mặc định | Dùng khi |
|---|---|---|---|
| `getResource(name)` | `URL` hoặc `null` | Parent trước, rồi current loader | Xem bản được chọn |
| `getResources(name)` | `Enumeration<URL>` | Parent candidates rồi local candidates | Liệt kê duplicates |
| `resources(name)` | `Stream<URL>` | Dựa trên `getResources` | Stream processing |
| `getResourceAsStream(name)` | `InputStream` hoặc `null` | Đọc bản được `getResource` chọn | Xem bytes được tiêu thụ |
| `findResource(name)` | Protected `URL`/`null` | Local search | Loader implementation/debug |
| `findResources(name)` | Protected enumeration | Local search | Debug child-only candidates |
| `SomeClass.class.getResource(name)` | `URL`/`null` | Relative/absolute + module context | File đi kèm class |
| `ClassLoader.getSystemResource(name)` | `URL`/`null` | System/built-in path | System resources |

## 4. Thứ tự nào thắng trong URLClassLoader?

### 4.1. Parent-first không thể bị thay chỉ bằng đảo URL của child

Giả sử:

~~~text
Parent loader:
  order.txt -> HOST

Child loader:
  URL #1: a.jar -> JAR_A
  URL #2: b.jar -> JAR_B
~~~

Kết quả theo default policy:

~~~text
child.getResource(name)  -> HOST
child.getResources(name) -> HOST > JAR_A > JAR_B
child.findResource(name) -> JAR_A
child.findResources(name)-> JAR_A > JAR_B
~~~

Nếu đổi thứ tự URL của child thành B rồi A:

~~~text
child.getResource(name)  -> HOST
child.getResources(name) -> HOST > JAR_B > JAR_A
child.findResource(name) -> JAR_B
child.findResources(name)-> JAR_B > JAR_A
~~~

Lý do: **parent đã thắng trước khi child được hỏi** ở `getResource`. Sửa thứ tự URL chỉ có tác động khi tới bước tra local resources của child.

### 4.2. Thứ tự URL trong chính URLClassLoader là có hợp đồng

Theo constructor của Java SE 21 `URLClassLoader`, URLs được search **theo thứ tự đưa vào**, sau bước search ở parent. Trong ví dụ `URL[] {jarA,jarB}`, child-local resource `JAR_A` đứng trước `JAR_B`; đổi array đảo vị trí.

Nhưng không suy luận rằng mọi framework classloader có cùng chính sách. Các hệ OSGi, servlet/container loaders, plugin engines hoặc Spring Boot launchers có thể dùng custom delegation và protocol/packaging.

### 4.3. `parent=null` không phải “tách quyền” hoặc “không có Java API”

Một `URLClassLoader` có parent `null` vẫn có thể nhờ bootstrap/VM built-in search nạp Java platform classes. Nó chỉ **không dùng application parent** theo cấu hình đó. Không coi `null` parent là security sandbox.

Trong thí nghiệm, vì bootstrap không có resource demo, loader này chọn `JAR_A` trực tiếp, sau đó `JAR_B`.

## 5. Chương trình thực hành Java 17+ có kết quả kiểm chứng

Ví dụ có bốn file text nhưng chỉ ba bản có tên trùng. Tất cả nội dung là nhãn ngắn, giúp chứng minh thứ tự mà không in absolute URL phụ thuộc máy.

### 5.1. Cây thư mục

~~~text
demo/
├── src/demo/host/ResourceOrderDemo.java
├── assets/
│   ├── a/sample/diagnostics/order.txt  (JAR_A)
│   └── b/sample/diagnostics/order.txt  (JAR_B)
└── build/
    ├── host/
    │   ├── demo/host/ResourceOrderDemo.class
    │   ├── demo/host/local.txt          (LOCAL)
    │   └── sample/diagnostics/order.txt (HOST)
    ├── a.jar
    └── b.jar
~~~

Tên resource đang kiểm tra: `sample/diagnostics/order.txt`. `local.txt` chỉ để chứng minh quy tắc tương đối của `Class.getResource`.

### 5.2. File `src/demo/host/ResourceOrderDemo.java`

~~~java
package demo.host;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

public class ResourceOrderDemo {
    static final String NAME = "sample/diagnostics/order.txt";

    static String label(URL url) throws IOException {
        if (url == null) return "NONE";
        try (InputStream input = url.openStream();
             BufferedReader reader = new BufferedReader(
                     new InputStreamReader(input, StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }

    static String labels(Enumeration<URL> found) throws IOException {
        List<String> result = new ArrayList<>();
        while (found.hasMoreElements()) {
            result.add(label(found.nextElement()));
        }
        return String.join(">", result);
    }

    static final class InspectableLoader extends URLClassLoader {
        InspectableLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        URL localFirst() {
            return findResource(NAME);
        }

        String localAll() throws IOException {
            return labels(findResources(NAME));
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = ResourceOrderDemo.class.getClassLoader();
        URL jarA = Path.of("build/a.jar").toUri().toURL();
        URL jarB = Path.of("build/b.jar").toUri().toURL();

        try (InspectableLoader ab = new InspectableLoader(
                     new URL[]{jarA, jarB}, parent);
             InspectableLoader ba = new InspectableLoader(
                     new URL[]{jarB, jarA}, parent);
             InspectableLoader independent = new InspectableLoader(
                     new URL[]{jarA, jarB}, null)) {

            System.out.println("parentFirst="
                    + label(ab.getResource(NAME)));
            System.out.println("allParentFirst="
                    + labels(ab.getResources(NAME)));
            System.out.println("childOnlyFirst="
                    + label(ab.localFirst()));
            System.out.println("childOnlyAll=" + ab.localAll());

            System.out.println("reversedStillParent="
                    + label(ba.getResource(NAME)));
            System.out.println("reversedAll="
                    + labels(ba.getResources(NAME)));

            System.out.println("noAppParentFirst="
                    + label(independent.getResource(NAME)));
            System.out.println("noAppParentAll="
                    + labels(independent.getResources(NAME)));

            System.out.println("absoluteClassResource="
                    + label(ResourceOrderDemo.class
                            .getResource("/" + NAME)));
            System.out.println("relativeClassResource="
                    + label(ResourceOrderDemo.class
                            .getResource("local.txt")));

            System.out.println("missingEnumerationEmpty="
                    + !ab.getResources(
                            "sample/diagnostics/absent.txt")
                             .hasMoreElements());

            try (InputStream stream = ab.getResourceAsStream(NAME)) {
                System.out.println("streamUsesParent="
                        + (stream != null
                           && "HOST".equals(new String(
                              stream.readAllBytes(),
                              StandardCharsets.UTF_8).trim())));
            }
        }
    }
}
~~~

### 5.3. Giải thích chương trình

- `label(url)` mở đúng URL qua `openStream`, đọc dòng đầu và đóng stream.
- `labels(enumeration)` duyệt **hết** resource candidates, không chỉ resource đầu tiên.
- `InspectableLoader` chỉ thêm hai wrapper để gọi `findResource`/`findResources`; nó không override parent-first policy.
- `ab` nhận URL A trước B, parent là host application loader.
- `ba` nhận URL B trước A, parent vẫn là host application loader.
- `independent` có parent `null`; bootstrap search vẫn tồn tại nhưng không chứa resource demo.
- `Class.getResource("/" + NAME)` dùng root-relative lookup; `getResource("local.txt")` dùng relative package lookup.
- Tên nonexistent trả enumeration rỗng.
- `getResourceAsStream` được so trực tiếp với nội dung `HOST`.

Chúng ta **không dùng `getURLs()` để chứng minh URL nào thực sự thắng**; `getURLs()` chỉ cho biết search path local. Kết quả `getResource` và từng URL từ `getResources` mới cho thấy những bản được chọn/liệt kê.

### 5.4. Linux/macOS: tạo resources, đóng JAR, chạy

Trước tiên lưu file Java ở mục 5.2, rồi chạy trong directory `demo`:

~~~sh
mkdir -p src/demo/host
mkdir -p build/host/sample/diagnostics
mkdir -p build/host/demo/host
mkdir -p assets/a/sample/diagnostics
mkdir -p assets/b/sample/diagnostics

printf 'HOST'  > build/host/sample/diagnostics/order.txt
printf 'LOCAL' > build/host/demo/host/local.txt
printf 'JAR_A' > assets/a/sample/diagnostics/order.txt
printf 'JAR_B' > assets/b/sample/diagnostics/order.txt

javac --release 17 -d build/host src/demo/host/ResourceOrderDemo.java
jar --create --file build/a.jar -C assets/a .
jar --create --file build/b.jar -C assets/b .
java -cp build/host demo.host.ResourceOrderDemo
~~~

**Lưu ý:** application classpath chỉ chứa `build/host`, không chứa `build/a.jar` hay `build/b.jar`. Hai JAR do child loaders quản lý và chỉ được đưa qua `URL[]`.

### 5.5. Windows PowerShell: tạo file UTF-8 không BOM

~~~powershell
New-Item -ItemType Directory -Force src/demo/host | Out-Null
New-Item -ItemType Directory -Force build/host/sample/diagnostics | Out-Null
New-Item -ItemType Directory -Force build/host/demo/host | Out-Null
New-Item -ItemType Directory -Force assets/a/sample/diagnostics | Out-Null
New-Item -ItemType Directory -Force assets/b/sample/diagnostics | Out-Null

$enc = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText("build/host/sample/diagnostics/order.txt", "HOST", $enc)
[System.IO.File]::WriteAllText("build/host/demo/host/local.txt", "LOCAL", $enc)
[System.IO.File]::WriteAllText("assets/a/sample/diagnostics/order.txt", "JAR_A", $enc)
[System.IO.File]::WriteAllText("assets/b/sample/diagnostics/order.txt", "JAR_B", $enc)

javac --release 17 -d build/host src/demo/host/ResourceOrderDemo.java
jar --create --file build/a.jar -C assets/a .
jar --create --file build/b.jar -C assets/b .
java -cp build/host demo.host.ResourceOrderDemo
~~~

Việc dùng UTF-8 không BOM tránh nội dung text có ký tự BOM làm thay đổi nhãn. Chương trình Java không cần file manifest có `Main-Class`, vì entry point `demo.host.ResourceOrderDemo` được chỉ rõ cho `java -cp`.

### 5.6. Stdout chính xác đã được kiểm chứng

~~~text
parentFirst=HOST
allParentFirst=HOST>JAR_A>JAR_B
childOnlyFirst=JAR_A
childOnlyAll=JAR_A>JAR_B
reversedStillParent=HOST
reversedAll=HOST>JAR_B>JAR_A
noAppParentFirst=JAR_A
noAppParentAll=JAR_A>JAR_B
absoluteClassResource=HOST
relativeClassResource=LOCAL
missingEnumerationEmpty=true
streamUsesParent=true
~~~

Đây là stdout của chương trình Java thực tế đã biên dịch thành công với `javac --release 17`; test đọc tài nguyên từ host directory và hai JAR, không dựa vào suy đoán classpath order.

### 5.7. Phân tích từng kết quả

| Output | Ý nghĩa |
|---|---|
| `parentFirst=HOST` | Parent-first `getResource` chọn bản của application loader |
| `allParentFirst=HOST>JAR_A>JAR_B` | `getResources` thêm các bản của child sau parent |
| `childOnlyFirst=JAR_A` | `findResource` chọn A trong local URL list |
| `childOnlyAll=JAR_A>JAR_B` | `findResources` liệt kê local candidates A rồi B |
| `reversedStillParent=HOST` | Đảo child URL không đổi bản parent thắng |
| `reversedAll=HOST>JAR_B>JAR_A` | Đảo child URLs làm đổi phần enumerate ở child |
| `noAppParentFirst=JAR_A` | Loader parent `null` không hỏi application loader |
| `noAppParentAll=JAR_A>JAR_B` | Independent child nhìn hai JAR theo URL order |
| `absoluteClassResource=HOST` | Class-relative API với `/` đầu chọn path từ root |
| `relativeClassResource=LOCAL` | Class-relative lookup thêm package `demo/host/` |
| `missingEnumerationEmpty=true` | Không tìm thấy là enumeration rỗng |
| `streamUsesParent=true` | `getResourceAsStream` đọc bản mà parent-first đã chọn |

Kết luận từ ví dụ: **muốn biết bản thắng thì xem `getResource`; muốn tìm toàn bộ nguyên nhân cạnh tranh thì dùng `getResources`**. Không mặc định đảo URL của child sẽ override resource ở parent.

## 6. `Class.getResource` và `ClassLoader.getResource` khác nhau ở dấu slash

Một nguồn lỗi rất phổ biến là truyền cùng chuỗi cho hai API khác nhau:

~~~java
Class<?> type = demo.host.ResourceOrderDemo.class;

URL absolute = type.getResource("/sample/diagnostics/order.txt");
URL relative = type.getResource("local.txt");

ClassLoader loader = type.getClassLoader();
URL loaderAbsolute = loader.getResource(
        "sample/diagnostics/order.txt");
~~~

Đây là snippet trong method, không phải file độc lập.

- `Class.getResource("/x/y")`: có `/` đầu, class-level API hiểu là resource name tuyệt đối theo root.
- `Class.getResource("local.txt")`: không có `/`, được hiểu tương đối với package của class `demo.host`, thành `demo/host/local.txt`.
- `ClassLoader.getResource("x/y")`: tên resource tính từ root, **không** tự thêm package và thông thường **không truyền leading slash**.
- `ClassLoader.getResource("/x/y")`: không bảo đảm hoạt động như `Class.getResource("/x/y")`; tránh nhầm cú pháp.

Khi ứng dụng dùng **named modules**, `Class.getResource` còn gắn với module context và quy tắc encapsulation tương ứng, vì vậy không phải mọi trường hợp đều tương đương một cuộc tìm toàn loader.

## 7. Tài nguyên trong JPMS named modules: giới hạn nhìn thấy

### 7.1. Tìm toàn ClassLoader không luôn thấy mọi resource có trong module

Javadoc Java SE 21 `ClassLoader.getResource` và `getResources` đặt ra quy tắc đối với **named modules**. Ngoại trừ tên kết thúc bằng `.class`, resource trong package của named module chỉ được công bố qua loader-wide APIs nếu package được **opened unconditionally** theo yêu cầu API.

Điều này tạo các khả năng:

- Entry có trong modular JAR nhưng `getResources` không trả URL vì package bị encapsulated.
- Package chỉ opened cho một module đích không có nghĩa loader-wide API được phép công bố resource như unconditional open.
- `Module.getResourceAsStream` hoặc `SomeClass.class.getResource` có ngữ cảnh access riêng; xem Javadoc tương ứng.
- “Không thấy resource qua loader” có thể là **vấn đề encapsulation**, không chỉ là file thiếu.

### 7.2. Thứ tự giữa nhiều modules cùng loader có thể không xác định

Javadoc lưu ý rõ rằng khi **nhiều named modules được định nghĩa trong cùng ClassLoader** và chúng chứa resource trùng tên, **thứ tự tìm modules không được chỉ định và có thể rất khó đoán**.

Do đó, không suy output `HOST>JAR_A>JAR_B` của `URLClassLoader` demo thành một cam kết cho mọi `ModuleLayer`.

Nếu ứng dụng cần file thuộc **một named module cụ thể**, dùng API truy cập theo module hoặc thiết kế resource path duy nhất; đừng dựa vào thứ tự module enumeration không ổn định.

### 7.3. Khi chẩn đoán modules

Kiểm tra:

1. Module đã được resolve vào runtime layer chưa?
2. Class loader đang được dùng định nghĩa modules nào?
3. Resource nằm trong package có `opens` hay `exports` phù hợp? `exports` một mình không thay thế `opens` cho resource encapsulation.
4. Caller đang dùng `Class.getResource`, `ClassLoader.getResources` hay `Module.getResourceAsStream`?
5. Nhiều named modules có cùng resource path trong cùng loader không?

Nhớ rằng `ModuleLayer` và ClassLoader có quan hệ mapping, **không phải danh sách file classpath tuyến tính đơn giản**.

## 8. Trùng `META-INF/services` và Java ServiceLoader

Ví dụ:

~~~text
a.jar:
  META-INF/services/com.example.spi.Processor
    com.vendor.alpha.AlphaProcessor

b.jar:
  META-INF/services/com.example.spi.Processor
    com.vendor.beta.BetaProcessor
~~~

Đây là mô tả nội dung, không phải code Java. Hai JAR chứa **cùng resource name** là thiết kế bình thường cho Java SPI.

`ServiceLoader` có thể đọc **nhiều provider configuration files** tương ứng với một service type và tìm các provider classes được khai báo. Vì vậy:

- Không kết luận chỉ provider trong resource đầu tiên mới được dùng.
- Không xóa ngẫu nhiên các `META-INF/services` trùng tên khi đóng fat/uber JAR.
- Khi shade nhiều JAR, cần **merge provider descriptors** theo build tool/resource transformer thích hợp.
- Chú ý service class identity: nếu host và plugin có hai bản runtime interface cùng tên do loaders khác nhau định nghĩa, provider có thể báo lỗi subtype/configuration.
- Nếu nhiều providers tồn tại, ứng dụng nên có **policy chọn provider** rõ; không coi thứ tự discovery là độ ưu tiên mà framework không cam kết.

Thực tế một số resource types phải **merge**, còn config chính của ứng dụng nên **được đặt tên riêng** hoặc chọn theo một policy có căn cứ. `getResources` là công cụ phát hiện; cách xử lý phụ thuộc ngữ nghĩa resource.

## 9. Quy trình chẩn đoán trong dự án thật

### 9.1. In đúng candidates của loader được dùng ở runtime

~~~java
static void inspect(ClassLoader loader, String name)
        throws IOException {
    URL winner = loader.getResource(name);
    System.out.println("winner=" + winner);

    Enumeration<URL> all = loader.getResources(name);
    int count = 0;
    while (all.hasMoreElements()) {
        URL candidate = all.nextElement();
        System.out.println("candidate[" + count++ + "]=" + candidate);
    }
    System.out.println("count=" + count);
}
~~~

Đây là **snippet method**, cần `URL`, `Enumeration` và `IOException` imports. Gọi với **đúng loader của code gây lỗi**, không nhất thiết là system ClassLoader.

Ba loader dễ nhầm:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader defining = SomeType.class.getClassLoader();
~~~

Snippet yêu cầu `SomeType` tồn tại. TCCL có thể được framework đổi theo worker/request; resource lookup từ `SomeType.class.getResource` không tự đồng nghĩa dùng TCCL. Với `ServiceLoader`, overload `load(service)` thường dựa trên TCCL, còn `load(service, loader)` dùng loader chỉ định.

### 9.2. Đọc nội dung, không chỉ in URL

~~~java
try (InputStream in = candidate.openStream()) {
    byte[] bytes = in.readAllBytes();
    System.out.println("resourceLength=" + bytes.length);
}
~~~

Đây là snippet có `candidate` URL và xử lý exceptions. Với file cấu hình có credentials, **không log toàn bộ nội dung**. Nếu muốn xác định hai candidates có cùng bytes hay không, có thể tính SHA-256 và so hashes; không coi URL string là checksum.

Với large binary resources, nên hash dạng streaming thay vì `readAllBytes` để tránh allocation không cần thiết.

### 9.3. Kiểm tra deployment, không chỉ build dependency graph

Những nguồn làm kết quả khác IDE:

- Lệnh `java -cp` hoặc `java -jar`, module path và launcher script thật.
- `Class-Path` manifest, external JAR dependencies và resource roots.
- Gradle/Maven runtime classpath khác compile/test classpath.
- Wildcard như `lib/*`: **không dựa vào thứ tự mở rộng không được cam kết**.
- Fat/shaded JAR merge/overwrite files; nested-JAR launcher có search semantics riêng.
- Parent/child loader graph trong application server/plugin container.
- Custom ClassLoader override `getResource` hoặc `getResources`.
- Cached config in memory, classloader lifecycle và TCCL trên thread pool.
- Module encapsulation, package `opens`, module layer mapping.

Nếu resource chỉ sai sau deploy, in **all candidate URLs ngay trong process deploy** và kiểm tra các JAR chứa entries qua:

~~~sh
jar --list --file path/to/app.jar
jar --list --file path/to/dependency.jar
~~~

Đây là các lệnh minh họa; thay paths bằng artifacts thực. Lệnh `jar --list` xem contents trên disk; `getResources` cho biết contents **được loader thấy trong process**. Hai tập này có thể khác vì cách launch.

### 9.4. Thứ tự điều tra đề xuất

1. Ghi **tên resource logic chính xác**, phân biệt slash/package-relative.
2. Xác định **loader được API đang lỗi sử dụng**: defining, context, system hoặc framework loader riêng.
3. Gọi `getResource` để in URL thắng.
4. Gọi `getResources` để liệt kê theo đúng thứ tự.
5. So URL với nội dung từng candidate, không chỉ tên JAR.
6. Kiểm tra parent loader search path và URL order của child.
7. Đối chiếu runtime command, repackaging/shading, module path và resource access.
8. Xem library/config framework có merge mọi candidates hay chỉ lấy một.
9. Sửa bằng **resource namespace riêng**, dependency cleanup, transformer hoặc lựa chọn URL tường minh — thay vì sửa order tùy tiện.
10. Test lại trên artifact phát hành thật và thêm regression test phát hiện duplicate sai chính sách.

### 9.5. Lưu ý về caching

Một ứng dụng có thể đọc resource một lần lúc startup rồi cache object cấu hình. Khi file disk đổi, `getResources` có thể vẫn trỏ cùng URL, trong khi ứng dụng tiếp tục dùng parsed state cũ. Một loader/JAR connection có thể có caching và lifecycle riêng; phải xem API và cấu hình launcher thực tế.

**Liệt kê URLs không đồng nghĩa reload thành công.** Nếu code/framework đã cache, cần cơ chế reload theo contract của framework, hoặc restart/recreate loader/process khi hợp lý.

## 10. Các lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/hướng xử lý |
|---|---|---|
| `getResource` chọn bản HOST thay vì plugin | Parent-first | In parent candidates; đặt tên resource riêng |
| `getResources` có 3 URLs | Trùng tên ở parent và child | Đọc nội dung, đừng tự xóa |
| Đảo thứ tự JAR_A/JAR_B nhưng bản thắng vẫn HOST | Parent đã thắng | Thay policy/path, không chỉ đảo child URLs |
| `getResources` không thấy entry có trong modular JAR | Named module encapsulation hoặc module chưa resolve | Kiểm tra module `opens`, layer, API gọi |
| `Class.getResource("x")` trả null | Relative path bị thêm package | Dùng `"/x"` nếu muốn root-absolute |
| `ClassLoader.getResource("/x")` trả null | Leading slash không giống class-relative API | Dùng `"x"` |
| Hai `META-INF/services` cùng tên | Nhiều SPI providers hợp lệ | Merge descriptors/kiểm tra providers |
| `ServiceLoader` báo `not a subtype` | API runtime identity chia đôi giữa loaders | Shared API từ parent, inspect Class objects |
| `getResources` rỗng nhưng JAR có file | Loader không thấy JAR, path sai, module access hoặc custom policy | In loader URLs, kiểm tra archive/module |
| Chạy IDE đúng, container sai | Classpath/launcher/framework khác | In runtime URLs và actual command |
| Thay file nhưng config không đổi | Cached parsed config/JAR connection/old loader | Kiểm tra lifecycle/reload |
| Nhiều modules cùng loader, thứ tự thay đổi | Module search order không được bảo đảm | Chọn module cụ thể, tránh priority theo index |
| Tìm đúng URL nhưng nội dung không như kỳ vọng | Artifact deploy/version khác hoặc duplicate byte content | Hash từng candidate |
| `findResources` ít entries hơn `getResources` | Không bao gồm parent | Hành vi được thiết kế |

**Các nhận định sai cần nhớ:**

1. `getResource` trả một URL không chứng minh chỉ có một resource.
2. `getResources` không trả `null` khi resource vắng mặt; trả enumeration rỗng.
3. `getResourceAsStream` không tự merge nhiều bản cấu hình.
4. Parent-first mặc định không giống child-first của một số frameworks.
5. URL thứ nhất của child không thể thắng parent nếu parent đã chọn.
6. `findResources` không tự đưa parent vào enumeration.
7. Cùng resource name không buộc cùng content.
8. `Class.getResource` và `ClassLoader.getResource` không có cùng quy tắc relative name.
9. Đường `jar:file:...!/entry` là URL, không phải resource name truyền vào.
10. Resource trong named module không phải lúc nào cũng được công bố qua loader-wide lookup.
11. Thứ tự giữa modules cùng loader không được bảo đảm chung.
12. Nhiều `META-INF/services` có thể là thiết kế đúng.
13. `ClassLoader.getSystemClassLoader()` không nhất thiết là loader đang tìm resource cho plugin.
14. Thứ tự build dependencies không nhất thiết bằng URL order ở production.
15. Không nên ghi URLs chứa secrets/credentials vào logs công khai.
16. Một container thay đổi launcher có thể đổi hoàn toàn thứ tự resources.
17. Có URL resource đúng không đồng nghĩa framework đã parse và reload nó.
18. `URLClassLoader.close()` ảnh hưởng lifecycle/resources nhưng không tự reload mọi config.

## 11. Tự kiểm tra kiến thức

1. `getResource` và `getResources` trả về loại dữ liệu nào?
2. Nếu không có resource, mỗi API phản hồi ra sao?
3. Vì sao `parentFirst=HOST` khi child có cả A và B?
4. Vì sao `allParentFirst=HOST>JAR_A>JAR_B`?
5. Tại sao `findResources` của child không liệt kê HOST?
6. Đảo URL order A/B thay đổi những dòng nào trong demo?
7. Parent `null` nghĩa là không còn Java built-in class loader không?
8. `getResourceAsStream` đọc mọi bản hay một bản?
9. `Class.getResource("local.txt")` xây path gì khi class ở package `demo.host`?
10. Nên dùng tên có slash đầu với Class-level hay ClassLoader-level API?
11. Làm thế nào kiểm tra hai URL có bytes giống nhau?
12. Có nên so URL string để xác thực integrity không?
13. `ClassLoader.resources(name)` có quan hệ gì với `getResources`?
14. Tại sao không nên dựa vào thứ tự classpath wildcard?
15. Khi nào nhiều `META-INF/services` cùng tên là bình thường?
16. ServiceLoader có nhất thiết chỉ đọc descriptor đầu tiên không?
17. Named module `opens` liên quan gì tới resource lookup?
18. Vì sao không thể suy thứ tự URLClassLoader demo sang mọi ModuleLayer?
19. System, TCCL và defining loader có thể khác nhau không?
20. Trong container, cần in log những giá trị nào để biết resource bản nào thắng?
21. Thay JAR trên disk có bảo đảm parsed configuration trong memory đổi ngay không?
22. Nếu framework merge nhiều resources, lựa chọn đầu tiên còn là nguyên nhân duy nhất không?
23. Cách viết một method in tất cả candidates mà không phụ thuộc IDE là gì?
24. Khi nào nên dùng path namespace riêng thay vì đổi URL order?
25. `getResources` rỗng trong khi JAR có entry có thể do những nguyên nhân nào?

**Tiêu chí hoàn thành:** tạo ba bản `sample/diagnostics/order.txt`, chạy và giải thích đủ 12 dòng output Java 17; tự liệt kê mọi URL trùng tên, chỉ ra bản thắng và nguyên nhân theo parent/child ordering, và nhận diện giới hạn JPMS/SPI/custom loaders.

## 12. Nguồn chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): resource path names, `getResource`, `getResources`, `findResources`, `resources`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): parent search, thứ tự URLs truyền constructor, close.
- [Java SE 21 — Class.getResource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): relative/absolute name và module context.
- [Java SE 21 — Module.getResourceAsStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): module resource encapsulation.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider files và discovery.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): classpath và module path khi chạy ứng dụng.

**Kết luận:** `getResource` chỉ chỉ ra **bản được chọn**, còn `getResources` giúp bạn thấy **toàn bộ ứng viên và thứ tự thực tế** của loader. Phải quan sát trong JVM đang chạy, với đúng loader, và xem nguồn bytes mỗi URL nếu cần. Đừng suy thứ tự từ tên file, dependency declaration hay tưởng mọi loader/JPMS module đều tìm theo cùng một quy luật.