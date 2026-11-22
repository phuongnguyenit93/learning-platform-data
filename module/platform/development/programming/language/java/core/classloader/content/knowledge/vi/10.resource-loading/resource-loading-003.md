# ClassLoader.getResource: đường dẫn tính từ gốc tài nguyên

## 1. Vấn đề: “gốc tài nguyên” là gốc nào?

Trong Java, **ClassLoader.getResource(String name)** giúp tìm dữ liệu đóng gói cùng chương trình như file cấu hình, template, ảnh, chứng chỉ công khai hoặc file văn bản. Tài nguyên được nhận diện bởi **tên đường dẫn phân tách bằng dấu /**, chẳng hạn:

~~~text
config/app.properties
templates/email.html
images/logo.png
com/example/messages.txt
~~~

Điểm quan trọng: **ClassLoader.getResource tìm tên tài nguyên tương đối với các gốc tìm kiếm của class loader**, không tự thêm tên package của class đang gọi. Vì vậy:

~~~java
ClassLoader loader = Example.class.getClassLoader();
URL url = loader.getResource("config/app.properties");
~~~

Tên **config/app.properties** được tìm tại **gốc của từng classpath entry / nguồn tài nguyên mà loader quản lý**. Nó không mặc định trở thành **com/example/config/app.properties** chỉ vì Example ở package com.example. Đây cũng không phải đường dẫn tuyệt đối của hệ điều hành, cũng không tự suy ra từ current working directory.

**Mục tiêu bài học:** chọn đúng resource name, phân biệt API của Class và ClassLoader, đọc stream an toàn, hiểu parent delegation và resource trong JAR/module, xử lý nhiều resource trùng tên, và chẩn đoán tại sao tài nguyên có trong project mà runtime vẫn trả về null.

## 2. Tên tài nguyên tương ứng với vị trí nào?

Giả sử chương trình sau khi build có cấu trúc:

~~~text
out/
├── demo/
│   ├── ResourceRootDemo.class
│   └── local.txt
└── config/
    └── app.properties
~~~

Trong trường hợp thư mục **out** nằm trên application classpath, ta có:

| Resource name truyền vào ClassLoader | Nơi tìm trong entry out | Kỳ vọng |
| --- | --- | --- |
| **config/app.properties** | out/config/app.properties | Có |
| **demo/local.txt** | out/demo/local.txt | Có |
| **local.txt** | out/local.txt | Không, nếu chỉ có file ở demo/ |
| **demo/config/app.properties** | out/demo/config/app.properties | Không |
| **/config/app.properties** | Không phải tên tương đối đúng trong ví dụ thông thường | Thường không tìm thấy |
| **config\\app.properties** | Không dùng dấu backslash làm dấu phân cách resource | Không đúng cách ghi thông thường |

Gốc ở đây là **out** vì đó là classpath entry. Nếu classpath thay bằng một JAR, gốc tương ứng là **root của các entry trong JAR**. Nếu loader tùy biến lấy resources từ nguồn khác, “gốc” do loader đó quy định.

**Không cần và không nên thêm dấu /** ở đầu đối số của ClassLoader.getResource. Dấu slash đầu chỉ có ý nghĩa đặc biệt với **Class.getResource**, không phải quy tắc mà ClassLoader.getResource mặc định loại bỏ.

### 2.1 Dấu / là dấu phân tách chuẩn của resource name

Dù ứng dụng chạy trên Windows, resource name vẫn viết:

~~~java
loader.getResource("config/app.properties");   // Đúng
loader.getResource("demo/local.txt");          // Đúng
~~~

Không viết theo dạng đường dẫn máy Windows như:

~~~java
loader.getResource("C:\\project\\config\\app.properties"); // Không phải resource name phù hợp
loader.getResource("config\\app.properties");                  // Sai quy ước slash
~~~

Đối số **name** là tên logic của tài nguyên trong không gian tra cứu của loader. Nó không phải đường dẫn filesystem và không nhất thiết có thể chuyển thành **java.nio.file.Path**.

### 2.2 Classpath có thể có nhiều gốc

Ví dụ lệnh:

~~~bash
java -cp out:assets:lib/util.jar demo.Main
~~~

trên Linux/macOS; trên Windows, dấu phân cách classpath là **;**, không phải **:**:

~~~powershell
java -cp "out;assets;lib/util.jar" demo.Main
~~~

Loader có thể tìm một tên tài nguyên trong các nguồn thích hợp **out**, **assets**, **util.jar** và những nguồn do parent cung cấp. Không gắn resource name với một thư mục filesystem duy nhất.

**Lưu ý:** có nhiều kiểu class loader, module path và môi trường tùy biến; ví dụ classpath trên mô tả hành vi thông thường của application loader với unnamed module, không phải cam kết rằng mọi loader đều đọc cùng một danh sách thư mục.

## 3. API ClassLoader.getResource trả gì?

Chữ ký:

~~~java
public URL getResource(String name);
~~~

Khi thành công, API trả về **java.net.URL** trỏ đến vị trí có thể dùng để đọc resource. Khi không tìm được hoặc không được phép truy cập (theo các quy tắc thích hợp), phương thức trả **null**. Truyền **null** làm name có thể ném **NullPointerException** theo API.

Sử dụng an toàn:

~~~java
ClassLoader loader = MyClass.class.getClassLoader();
URL resource = loader.getResource("config/app.properties");

if (resource == null) {
    throw new IllegalStateException("Missing config/app.properties");
}

try (InputStream in = resource.openStream()) {
    // Đọc dữ liệu...
}
~~~

Đây là snippet để đặt trong ứng dụng có MyClass, imports và phần đọc dữ liệu; chưa là một chương trình độc lập. Phần 6 có ví dụ đủ file, lệnh chạy và stdout.

**URL không phải Path:** khi chạy từ thư mục, URL có thể bắt đầu bằng **file:**; khi đóng gói vào JAR, URL thường có dạng **jar:file:...!/config/app.properties**; tài nguyên hệ JDK có thể có dạng **jrt:**. Vì thế không nên lấy **url.getFile()** rồi ép thành **File** để đọc trong mọi môi trường.

## 4. So sánh ClassLoader.getResource và Class.getResource

Đây là nguồn gây nhầm lẫn lớn nhất.

### 4.1 Quy tắc của ClassLoader

Với ClassLoader:

~~~java
ClassLoader loader = Demo.class.getClassLoader();

URL a = loader.getResource("config/app.properties");
URL b = loader.getResource("demo/local.txt");
~~~

Tên truyền vào được hiểu là **tên đường dẫn từ gốc resource search**. Không có quy tắc tự ghép tên package **demo** vào trước resource name. Đừng đặt slash đầu chuỗi.

### 4.2 Quy tắc của Class

Với Class:

~~~java
URL a = Demo.class.getResource("local.txt");
URL b = Demo.class.getResource("/config/app.properties");
URL c = Demo.class.getResource("/demo/local.txt");
~~~

Nếu **Demo** thuộc package **demo**:

- **getResource("local.txt")**: tên không bắt đầu bằng slash, **Class** tạo tên tuyệt đối **demo/local.txt**.
- **getResource("/config/app.properties")**: tên bắt đầu bằng slash, **Class** bỏ slash đó rồi tra **config/app.properties** từ gốc.
- **getResource("/demo/local.txt")**: bỏ slash đầu, tra **demo/local.txt** từ gốc.

Như vậy, **Class.getResource("/demo/local.txt")** và **ClassLoader.getResource("demo/local.txt")** có thể cùng tìm một resource trong chương trình classpath đơn giản. Nhưng Class và ClassLoader không phải các API hoàn toàn đồng nhất: trong **named module**, Class.getResource gắn với module của Class và kiểm tra encapsulation theo quy tắc dành cho caller.

### 4.3 Bảng đối chiếu

Giả sử **demo/LocalDemo.class**, **demo/local.txt**, **config/app.properties** cùng ở một classpath root:

| Biểu thức | Tên được tìm trong ví dụ | Kết quả |
| --- | --- | --- |
| **loader.getResource("demo/local.txt")** | demo/local.txt | Tìm thấy |
| **loader.getResource("local.txt")** | local.txt | Không thấy |
| **loader.getResource("/demo/local.txt")** | Tên có slash đầu không được ClassLoader tự bỏ | Không thấy trong loader classpath thông thường |
| **LocalDemo.class.getResource("local.txt")** | demo/local.txt | Tìm thấy |
| **LocalDemo.class.getResource("/demo/local.txt")** | demo/local.txt | Tìm thấy |
| **LocalDemo.class.getResource("config/app.properties")** | demo/config/app.properties | Không thấy |
| **LocalDemo.class.getResource("/config/app.properties")** | config/app.properties | Tìm thấy |

**Quy tắc dễ nhớ:**

~~~text
ClassLoader.getResource("x/y.txt")
            |
            └─ x/y.txt tính từ gốc loader

Class.getResource("y.txt")
            |
            └─ package/của/Class/y.txt

Class.getResource("/x/y.txt")
            |
            └─ x/y.txt tính từ gốc (Class bỏ dấu / đầu)
~~~

Không dùng một biến API khác để “sửa” đường dẫn không đúng; hãy xác định xem tài nguyên được đóng gói ở root entry nào và API nào đáp ứng ý định.

## 5. Đường dẫn từ gốc không phải thư mục project đang mở

Câu hỏi thường gặp: “Tôi có file trong thư mục **src/main/resources**, tại sao getResource không nhận chuỗi **src/main/resources/config/app.properties**?”

Trong ứng dụng Maven/Gradle thông thường, file dưới **src/main/resources** được **copy thành resource output**, rồi thư mục output được đưa lên runtime classpath hoặc được đóng gói vào JAR:

~~~text
project/
├── src/main/java/demo/App.java
├── src/main/resources/
│   └── config/app.properties
└── target/classes/                 (ví dụ Maven)
    ├── demo/App.class
    └── config/app.properties
~~~

Resource name khi chạy thông thường là:

~~~java
loader.getResource("config/app.properties");
~~~

**Không phải:**

~~~java
loader.getResource("src/main/resources/config/app.properties");
~~~

vì tên nguồn **src/main/resources** không nằm trong cấu trúc resource runtime của artifact được build theo quy ước này.

Tương tự với Gradle, các task xử lý resources thường tạo output resources và đóng gói vào classpath/JAR. Cần kiểm tra artifact **thực tế** nếu build đã được cấu hình khác mặc định.

### 5.1 CWD chỉ có thể ảnh hưởng gián tiếp

Nếu bạn chạy:

~~~bash
java -cp out:assets demo.ResourceRootDemo
~~~

thì phần **out** và **assets** là các classpath entries dạng tương đối. Chúng được diễn giải tương đối với nơi chạy lệnh lúc khởi động JVM. **Nhưng resource name** vẫn là **config/app.properties**, không phải đường dẫn tương đối tùy ý tới thư mục làm việc.

Nếu đổi working directory khiến các path trong **-cp** không còn đúng, resource có thể mất. Nguyên nhân khi ấy nằm ở **classpath root được cấu hình**, không phải ClassLoader.getResource tự tìm bằng CWD.

## 6. Ví dụ chạy được số 1: kiểm tra root, package và dấu slash

Tạo cấu trúc thư mục:

~~~text
project/
├── src/
│   └── demo/
│       └── ResourceRootDemo.java
└── assets/
    ├── config/
    │   └── app.properties
    └── demo/
        └── local.txt
~~~

**assets/config/app.properties**:

~~~properties
mode=demo
~~~

**assets/demo/local.txt**:

~~~text
welcome-from-package
~~~

**src/demo/ResourceRootDemo.java**:

~~~java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class ResourceRootDemo {
    private static String readText(InputStream source) throws Exception {
        if (source == null) {
            return "<missing>";
        }

        try (InputStream in = source) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceRootDemo.class.getClassLoader();

        System.out.println("loader root = "
                + (loader.getResource("config/app.properties") != null));

        System.out.println("loader leading slash = "
                + (loader.getResource("/config/app.properties") != null));

        System.out.println("class relative = "
                + (ResourceRootDemo.class.getResource("local.txt") != null));

        System.out.println("class absolute = "
                + (ResourceRootDemo.class.getResource("/config/app.properties")
                        != null));

        System.out.println("class mistaken relative = "
                + (ResourceRootDemo.class.getResource("config/app.properties")
                        != null));

        Properties properties = new Properties();
        try (InputStream in = loader.getResourceAsStream(
                "config/app.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing properties");
            }
            properties.load(in);
        }

        System.out.println("mode = " + properties.getProperty("mode"));
        System.out.println("local = "
                + readText(loader.getResourceAsStream("demo/local.txt")));
    }
}
~~~

Đứng tại thư mục **project**, biên dịch:

~~~bash
javac -d out src/demo/ResourceRootDemo.java
~~~

Chạy trên Linux/macOS:

~~~bash
java -cp out:assets demo.ResourceRootDemo
~~~

Hoặc trên Windows PowerShell:

~~~powershell
java -cp "out;assets" demo.ResourceRootDemo
~~~

**Stdout kỳ vọng** với application classpath đúng như trên, resource files chính xác như ví dụ và không có resource cùng tên ở parent loader:

~~~text
loader root = true
loader leading slash = false
class relative = true
class absolute = true
class mistaken relative = false
mode = demo
local = welcome-from-package
~~~

### 6.1 Vì sao ra kết quả như vậy?

- **loader root = true**: file **assets/config/app.properties** nằm dưới root **assets**, và application loader nhận tên **config/app.properties**.
- **loader leading slash = false**: **ClassLoader.getResource** không chuyển chuỗi **/config/app.properties** thành root-relative như Class.getResource; loader classpath thông thường không tìm tên có slash đầu này.
- **class relative = true**: ResourceRootDemo thuộc package **demo**, nên **Class.getResource("local.txt")** tra **demo/local.txt**.
- **class absolute = true**: Class.getResource loại bỏ slash đầu và tra **config/app.properties**.
- **class mistaken relative = false**: Class.getResource không bỏ qua package khi tên không có slash; nó tra **demo/config/app.properties**, đường dẫn này không có.
- **mode** và **local** chứng minh resources được **đọc qua InputStream**, không cần biết chúng là file hệ điều hành hay entry trong archive.

### 6.2 Cách kiểm tra nếu stdout khác

Nếu mọi giá trị đều false, kiểm tra đúng working directory, classpath separator của OS, hai file tài nguyên có được tạo đúng không và classpath thực tế có mục **assets** không. Nếu chỉ một giá trị thay đổi bất ngờ, kiểm tra liệu có **resource trùng tên** trong parent loader/JAR khác hay custom loader làm khác quy tắc mặc định không.

**Quan trọng:** ví dụ dùng API của unnamed module trên classpath tiêu chuẩn. Trong named modules, cần xét thêm **module encapsulation** như phần 10.

## 7. Dùng getResourceAsStream: đọc dữ liệu, không cần biết URL

Trong nhiều trường hợp cần **nội dung** chứ không cần URL. ClassLoader có:

~~~java
public InputStream getResourceAsStream(String name);
~~~

Ví dụ ngắn trong một method có **loader** và exception handling:

~~~java
try (InputStream in = loader.getResourceAsStream(
        "config/app.properties")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource missing: config/app.properties"
        );
    }

    Properties props = new Properties();
    props.load(in);
}
~~~

Quy tắc:

- **Null** có nghĩa resource không tìm được hoặc không được cung cấp theo policy truy cập thích hợp.
- **InputStream phải đóng** sau khi đọc; dùng try-with-resources.
- **Properties.load(InputStream)** theo chuẩn dùng quy tắc mã hóa ISO-8859-1 và escaping của properties format. Nếu file cần UTF-8 không phải ASCII, cân nhắc **Properties.load(Reader)** với **InputStreamReader(..., UTF_8)** hoặc API parser phù hợp.
- Với file văn bản UTF-8 thông thường, dùng InputStreamReader / new String(bytes, UTF_8), không dựa vào default charset ngầm.
- Không gọi **available()** để suy ra tổng chiều dài tài nguyên; available chỉ thể hiện lượng byte có thể đọc ngay mà không block.
- Không mở lại stream nhiều lần nếu bạn có thể đọc một lượt và cache nội dung phù hợp.

### 7.1 Không chuyển URL thành File bằng mọi giá

Đoạn sau có thể chỉ hoạt động khi resource thật sự nằm trên filesystem:

~~~java
// KHÔNG dùng chung cho file/JAR/module:
File file = new File(url.getFile());
~~~

Khi đóng gói thành JAR, URL có thể có dạng:

~~~text
jar:file:/path/to/app.jar!/config/app.properties
~~~

Không có file hệ điều hành riêng tại **/path/to/app.jar!/config/app.properties**. Đây là entry bên trong archive. Tốt nhất đọc bằng **URL.openStream()** hoặc **ClassLoader.getResourceAsStream()**; chỉ chuyển thành **Path** nếu protocol và filesystem provider thực sự hỗ trợ, và bạn quản lý vòng đời filesystem tương ứng.

## 8. Đóng gói JAR không làm đổi resource name

Dùng cùng ví dụ phần 6, đứng tại **project** sau khi đã compile:

~~~bash
jar --create --file demo-resources.jar -C out . -C assets .
jar --list --file demo-resources.jar
~~~

Trong archive sẽ có những entry như:

~~~text
demo/ResourceRootDemo.class
demo/local.txt
config/app.properties
~~~

Các metadata entry như **META-INF/MANIFEST.MF** cũng có thể xuất hiện, nên danh sách trên chỉ liệt kê entry đang quan tâm.

Chạy JAR bằng classpath trên Linux/macOS hoặc Windows đều dùng một entry duy nhất:

~~~bash
java -cp demo-resources.jar demo.ResourceRootDemo
~~~

Stdout kỳ vọng **giống phần 6** vì resource name vẫn là **config/app.properties** và **demo/local.txt**. Loader chỉ thay nguồn lấy bytes: từ thư mục assets sang các JAR entries.

**Bài học:** không ghép tên file JAR vào đối số **getResource**:

~~~java
// Sai ý nghĩa khi muốn đọc entry:
loader.getResource("demo-resources.jar/config/app.properties");

// Đúng:
loader.getResource("config/app.properties");
~~~

Thay đổi cách đóng gói không bắt bạn thay resource name nếu **đường dẫn của resource bên trong root** giữ nguyên.

### 8.1 Giới hạn của ví dụ đóng gói

Nếu JAR được module hóa và đặt trên module path, quy tắc tìm non-class resources còn phụ thuộc named module và mức mở package. Ví dụ trên dùng plain classpath, không có **module-info.java**.

## 9. Parent delegation: ClassLoader.getResource tìm ở đâu trước?

Theo implementation mặc định trong ClassLoader API:

1. Tìm tài nguyên thông qua **parent loader**; nếu không có parent, tìm trên đường tra resource của bootstrap loader phù hợp.
2. Nếu parent không tìm thấy, gọi **findResource(name)** của loader hiện tại.
3. Trả URL đầu tiên tìm được, hoặc null nếu không có resource hợp lệ.

~~~text
child.getResource("config/app.properties")
             │
             ▼
   parent.getResource(name)
             │
       ┌─────┴──────┐
       │ found URL? │
       └─────┬──────┘
       true  │ false
         │   ▼
         │ child.findResource(name)
         │   │
         └───┤
             ▼
        return URL / null
~~~

**Quan trọng:** Một file nằm trong JAR của child loader chưa chắc được lấy nếu parent cũng có resource **cùng tên**; parent có thể thắng theo delegation mặc định. Đừng nghĩ tất cả resource trùng tên luôn được chọn từ entry gần nhất với class đang gọi.

### 9.1 findResource và getResource khác nhau

- **getResource(name)** là entry point public của loader, xử lý delegation theo hợp đồng mặc định.
- **findResource(name)** là hook protected được subclass override để tự tìm resource trong nguồn mà nó quản lý.
- **findResources(name)** là hook protected để tìm nhiều resource cùng tên trong nguồn của loader.
- Cài đặt custom loader có thể override getResource và chọn policy khác; khi đó cần kiểm tra implementation thực tế.

Một custom loader chỉ muốn thêm nguồn resource thông thường nên override **findResource** (và **findResources** nếu hỗ trợ multiple resources), đồng thời giữ delegation mặc định khi không có lý do rõ ràng để thay.

### 9.2 Resource lookup không đồng nghĩa class loading

**loader.getResource("demo/Widget.class")** có thể tìm được class-file bytes, nhưng việc tìm resource **không tự tạo một java.lang.Class** cho Widget. **ClassLoader.loadClass("demo.Widget")** là quá trình tìm/định nghĩa runtime type khác về ngữ nghĩa.

Ngược lại, một custom loader có thể cung cấp Class qua bytecode sinh trong bộ nhớ nhưng không cho **getResource("demo/Widget.class")** tìm được stream tương ứng. Không dùng getResource làm phép thử duy nhất để khẳng định một class sẽ load được.

## 10. Named modules: resource có tồn tại nhưng vẫn không được tìm thấy

Từ Java 9, named modules có cơ chế **encapsulation** đối với nhiều non-class resources. Với **ClassLoader.getResource(name)** và **ClassLoader.getResources(name)**, Javadoc quy định:

- Resources trong named modules chịu quy tắc encapsulation theo **Module.getResourceAsStream**.
- Ngoại trừ trường hợp tên kết thúc bằng **.class**, resource thuộc package của named module thường chỉ được API **ClassLoader.getResource** tìm thấy khi package đó được **opened unconditionally** (mở không điều kiện), ngay cả khi caller ở trong cùng module.
- Nếu không thỏa, **getResource** có thể trả null dù resource thực sự được đóng gói trong module.
- Nếu nhiều module do cùng loader định nghĩa có resource trùng tên, thứ tự tìm qua modules có thể không xác định.

Đây là khác biệt với ví dụ classpath đơn giản.

### 10.1 Ví dụ module-info.java minh họa

Giả sử named module **sample.resources** chứa tài nguyên tại package **sample.internal**, và bạn muốn **ClassLoader.getResource("sample/internal/settings.json")** có thể tìm được qua loader từ bên ngoài. Module declaration có thể viết:

~~~java
module sample.resources {
    opens sample.internal;
}
~~~

**opens sample.internal;** là mở package không điều kiện. Trong khi đó **opens sample.internal to another.module;** chỉ mở có điều kiện cho module được nêu, không đáp ứng quy tắc mở **unconditionally** của ClassLoader.getResource cho non-class resource.

Không nên mở mọi package chỉ để một đoạn code tùy ý đọc tài nguyên; module encapsulation có lý do về thiết kế API và giới hạn truy cập. Khi tài nguyên gắn với một module cụ thể và caller có quyền truy cập thích hợp, có thể cân nhắc **Class.getResourceAsStream** hoặc **Module.getResourceAsStream**, vốn có ngữ nghĩa module-aware và quy tắc caller tương ứng.

### 10.2 Class.getResource trong named module cũng có quy tắc riêng

Với một Class thuộc **named module**, **Class.getResource** tìm tài nguyên trong module của Class, chứ không chỉ tự thêm package rồi dựa trên classpath search chung. Nó còn áp dụng encapsulation theo quyền của caller. Vì vậy:

~~~java
SomeClass.class.getResource("/sample/internal/settings.json");
~~~

không phải phép biến đổi chắc chắn tương đương với:

~~~java
SomeClass.class.getClassLoader()
        .getResource("sample/internal/settings.json");
~~~

trong mọi named-module application. Tránh diễn giải máy móc quy tắc hai dấu slash khi đã có module boundaries.

## 11. getResources: nếu cùng tên có nhiều bản thì sao?

Một loader còn có API:

~~~java
public Enumeration<URL> getResources(String name) throws IOException;
~~~

Nó tìm **nhiều URL** cùng tên. Implementation mặc định tìm parent trước rồi bổ sung tài nguyên từ **findResources(name)** của loader hiện tại. Đây là công cụ hữu ích khi phát hiện resource bị JAR khác che khuất.

Java 9+ còn có:

~~~java
public Stream<URL> resources(String name);
~~~

Hàm stream lazy và có thể bọc lỗi I/O thành **UncheckedIOException** khi duyệt; nếu muốn code dễ kiểm soát checked exception, **getResources** vẫn là lựa chọn rõ ràng.

### 11.1 Ví dụ chạy được số 2: hai classpath roots có cùng tên

Tạo:

~~~text
project/
├── src/demo/ResourceOrderDemo.java
├── assets-a/demo/banner.txt
└── assets-b/demo/banner.txt
~~~

**assets-a/demo/banner.txt**:

~~~text
blue
~~~

**assets-b/demo/banner.txt**:

~~~text
green
~~~

**src/demo/ResourceOrderDemo.java**:

~~~java
package demo;

import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

public class ResourceOrderDemo {
    static String read(URL url) throws Exception {
        if (url == null) {
            return "<missing>";
        }

        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader =
                ResourceOrderDemo.class.getClassLoader();
        String name = "demo/banner.txt";

        System.out.println("first = " + read(loader.getResource(name)));

        Enumeration<URL> matches = loader.getResources(name);
        int count = 0;

        while (matches.hasMoreElements()) {
            count++;
            System.out.println("resource " + count + " = "
                    + read(matches.nextElement()));
        }

        System.out.println("count = " + count);
    }
}
~~~

Biên dịch:

~~~bash
javac -d out src/demo/ResourceOrderDemo.java
~~~

Linux/macOS:

~~~bash
java -cp out:assets-a:assets-b demo.ResourceOrderDemo
~~~

Windows PowerShell:

~~~powershell
java -cp "out;assets-a;assets-b" demo.ResourceOrderDemo
~~~

Với application classpath thông thường trong lệnh này, không có bản trùng do parent cung cấp, stdout kỳ vọng:

~~~text
first = blue
resource 1 = blue
resource 2 = green
count = 2
~~~

Nếu đảo thứ tự classpath roots:

~~~bash
java -cp out:assets-b:assets-a demo.ResourceOrderDemo
~~~

trên Linux/macOS, hoặc Windows:

~~~powershell
java -cp "out;assets-b;assets-a" demo.ResourceOrderDemo
~~~

thì bản được chọn đầu thường là **green**, và thứ tự enumeration đổi tương ứng, miễn loader tìm các classpath entries theo thứ tự cấu hình của ví dụ.

**Giới hạn:** Không được khái quát thứ tự trên cho **mọi custom loader** hay khi có **nhiều named modules** chứa cùng resource. Theo Javadoc, thứ tự search modules trong một loader có thể không xác định. Khi một dự án thực sự yêu cầu cấu hình ưu tiên rõ ràng, hãy thiết kế nguồn và quy tắc ưu tiên thay vì phụ thuộc ngẫu nhiên vào resource trùng tên.

### 11.2 Dùng getResources để chẩn đoán trùng file

Nếu ứng dụng dùng nhiều JAR và load nhầm **META-INF/services/...**, **config/defaults.properties** hoặc template, in các URLs từ getResources. Đừng in nguyên nội dung nhạy cảm; việc liệt kê URL đủ giúp biết resource nằm ở những nguồn nào. Kết quả có thể là **jar:** URL hoặc nguồn tùy biến khác.

## 12. Context class loader, system loader và loader của Class

Java có nhiều con đường chọn loader, không nên nhầm:

| Cách lấy loader | Thông thường dùng cho |
| --- | --- |
| **MyClass.class.getClassLoader()** | Defining loader của MyClass; phù hợp khi muốn resource gắn với component chứa MyClass. |
| **ClassLoader.getSystemClassLoader()** | System/application loader của tiến trình JVM. |
| **ClassLoader.getSystemResource(name)** | Resource lookup qua system loader. |
| **Thread.currentThread().getContextClassLoader()** | Loader được đặt vào thread để phục vụ một số framework, service provider và runtime container. |

Một thư viện chạy trong application server có thể được parent loader định nghĩa nhưng cần tìm resource của plugin qua **thread context class loader**. Khi đó resource có thể không được nhìn thấy qua loader của chính class thư viện.

Ví dụ minh họa đặt trong method (không phải một chương trình standalone):

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ClassLoader defining =
        SomeLibrary.class.getClassLoader();

URL fromContext = context == null ? null
        : context.getResource("plugin/settings.properties");

URL fromDefining = defining == null ? null
        : defining.getResource("plugin/settings.properties");
~~~

Hai URL có thể khác hoặc một bên null. Đừng chỉ đổi loader cho đến khi “hết null”; hãy làm rõ **resource thuộc component nào, ai sở hữu resource và runtime đang dùng loader nào**.

## 13. Chẩn đoán khi getResource trả null

Nếu bạn thấy:

~~~java
URL url = loader.getResource("config/app.properties");
// url == null
~~~

hãy kiểm tra có hệ thống.

### 13.1 Resource name có đúng từ root không?

Kiểm tra lỗi thừa/thiếu prefix:

- Sai với ClassLoader: **/config/app.properties** (slash đầu).
- Sai khi file đã được copy vào root: **src/main/resources/config/app.properties**.
- Sai khi file thực tế nằm trong package: **local.txt** thay vì **demo/local.txt**.
- Sai separator: **config\\app.properties** thay vì **config/app.properties**.

### 13.2 Resource đã được copy vào build output/JAR chưa?

Tồn tại trong Git repository **không chứng minh** nó đã được đóng gói vào artifact đang chạy. Kiểm tra thư mục output hay entries trong JAR:

~~~bash
jar --list --file demo-resources.jar
~~~

Dòng **config/app.properties** phải xuất hiện ở đúng root entry. Nếu dùng Maven/Gradle, kiểm tra nguồn resource, include/exclude filters và kết quả build.

### 13.3 Application chạy bằng classpath nào?

Phân biệt:

- Classpath khi compile với **javac**.
- Classpath khi launch bằng **java**.
- Module path nếu dùng named modules.
- Classpath trong IDE/test runner/container.

Việc compile được code **không đảm bảo** runtime launcher mang theo mọi file resource, vì compiler không nhất thiết đọc tài nguyên đó.

### 13.4 Đang hỏi đúng ClassLoader chưa?

So sánh:

~~~java
System.out.println(MyClass.class.getClassLoader());
System.out.println(ClassLoader.getSystemClassLoader());
System.out.println(Thread.currentThread().getContextClassLoader());
~~~

Đây là snippet đặt trong method với MyClass có thật. Kết quả loader khác nhau có thể hợp lệ; kiểm tra parent delegation và scope của plugin.

### 13.5 Có named module encapsulation không?

Đặc biệt với non-.class resources ở package của named modules: ClassLoader.getResource có thể không tìm thấy nếu package không được **opened unconditionally**, dù file tồn tại. Kiểm tra **module-info.java**, package của resource, nơi module được load và API caller đang dùng.

### 13.6 Tài nguyên có tên trùng bị che khuất không?

Nếu getResource trả URL nhưng nội dung “sai phiên bản”, dùng **getResources(name)** liệt kê các bản được tìm, xác minh thứ tự parent/classpath/JAR. Không giả định cùng filename chỉ có một bản trên classpath.

### 13.7 Có thực sự là lỗi I/O hay URL?

- **getResource == null**: thiếu resource, không được nhìn thấy hoặc không được phép theo API.
- **getResource trả URL nhưng url.openStream() lỗi**: tài nguyên có thể trở nên không truy cập được, archive bị đóng, vấn đề quyền hoặc I/O.
- **getResourceAsStream trả null**: không tự xem là stream rỗng; đây là dấu hiệu không tìm được/không có quyền truy cập.
- **name == null**: API báo NullPointerException, không phải “resource vắng mặt”.

Tách bước tìm tên khỏi bước mở và đọc stream để biết lỗi nằm ở đâu.

## 14. Resource lookup và bảo mật

Tài nguyên có thể chứa dữ liệu cấu hình nhạy cảm hoặc template có giá trị trong hệ thống, nhưng **ClassLoader.getResource không phải API bảo mật để che giấu bí mật**. Nếu đưa secret vào JAR, người có archive thường có thể đọc nội dung. Không đóng gói credentials hoặc private keys không được bảo vệ như resource công khai.

Nếu resource name đến từ input bên ngoài, hãy áp dụng allowlist và kiểm soát tên phù hợp. Không cho phép người dùng tùy ý truyền đường dẫn **../** rồi hy vọng loader tự ngăn mọi truy cập ngoài phạm vi. Trách nhiệm bảo vệ đường dẫn, tên nguồn và quyền truy cập còn phụ thuộc implementation cụ thể của custom loader và URL protocol.

Nếu tài nguyên lớn, cân nhắc streaming thay vì đọc tất cả bytes bằng **readAllBytes()**. Ví dụ dùng readAllBytes chỉ để code học tập ngắn và resource nhỏ. Đóng InputStream đúng cách bằng try-with-resources.

## 15. Tình huống thực hành và cách lựa chọn API

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Resource cố định ở root của component trên classpath | **MyClass.class.getClassLoader().getResource("config/app.properties")** nếu loader không null. |
| Resource nằm cạnh một class trong cùng package | **MyClass.class.getResource("local.txt")**. |
| Resource nằm từ root nhưng muốn gọi qua Class | **MyClass.class.getResource("/config/app.properties")**. |
| Chỉ cần đọc bytes/text | **getResourceAsStream** + try-with-resources. |
| Cần URL để một API khác mở tài nguyên | **getResource** rồi kiểm tra null và protocol; không coi luôn là File. |
| Nghi nhiều bản resource trùng tên | **getResources** / **resources**. |
| Resources của plugin không thuộc loader thư viện | Kiểm tra loader plugin hoặc thread context loader theo hợp đồng framework. |
| Named module có resource đóng kín | Cân nhắc **Module.getResourceAsStream** và quy tắc module openness, thay vì chỉ đổi dấu slash. |
| Resource nằm trên filesystem ngoài artifact | Dùng **Path/Files** với đường dẫn được cấu hình rõ; không đánh tráo với ClassLoader.getResource. |

**Phân biệt hai nguồn dữ liệu:**

~~~text
Filesystem external configuration:
    Path.of("/etc/myapp/config.yml")
    Files.newInputStream(path)

Classpath/module resource:
    loader.getResourceAsStream("config/defaults.yml")
~~~

Đây là hai mô hình phân phối khác nhau. Resources đóng gói thường phù hợp dữ liệu mặc định hoặc read-only; file external phù hợp cấu hình triển khai có thể thay đổi độc lập.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** App có class **com.example.Tool** và resource **com/example/help.txt**. Gọi **Tool.class.getClassLoader().getResource("help.txt")** có tự tìm dưới package com.example không?

**Đáp án:** Không. ClassLoader.getResource nhận tên từ root; hãy dùng **com/example/help.txt**, hoặc **Tool.class.getResource("help.txt")** nếu muốn tìm tương đối từ package.

**Câu 2.** Khi dùng ClassLoader, chuỗi **/config/app.properties** có ý nghĩa “tìm ở root” giống Class.getResource không?

**Đáp án:** Không. ClassLoader không áp dụng quy tắc bỏ slash đầu. Dùng **config/app.properties**. Với Class.getResource mới dùng slash đầu để chỉ root.

**Câu 3.** Vì sao resource tồn tại ở **src/main/resources/config/app.properties** nhưng code lại tìm **config/app.properties**?

**Đáp án:** Build thông thường copy nội dung của resources folder vào root resource output hoặc JAR. Tên src/main/resources không phải một phần của resource name runtime.

**Câu 4.** Đổi từ chạy thư mục classpath sang chạy JAR có buộc đổi đối số getResource không?

**Đáp án:** Không nếu đường dẫn entry bên trong root vẫn như cũ. API trả URL với scheme khác, nhưng resource name giữ nguyên.

**Câu 5.** Vì sao gọi **new File(url.getFile())** không đọc được resource bên trong JAR?

**Đáp án:** Entry JAR không tồn tại như file riêng ngoài filesystem. Hãy dùng **URL.openStream** hoặc **getResourceAsStream**.

**Câu 6.** Loader con có config.txt, parent cũng có config.txt. Với implementation ClassLoader mặc định, bản nào thường được tìm trước?

**Đáp án:** Parent trước, sau đó loader con gọi findResource nếu chưa tìm được.

**Câu 7.** Resource trong named module có thể tồn tại mà ClassLoader.getResource trả null không?

**Đáp án:** Có. Non-.class resources trong package của named module có thể bị module encapsulation che khuất nếu package không được opened unconditionally.

**Câu 8.** ClassLoader.getResource trả URL nhưng nội dung không đúng bản. API nào giúp tìm các bản trùng tên?

**Đáp án:** **getResources(name)** (hoặc **resources(name)** trên Java 9+), rồi kiểm tra từng nguồn.

**Câu 9.** Có thể xác nhận **loadClass("com.example.Tool")** sẽ thành công chỉ nhờ getResource("com/example/Tool.class") trả URL?

**Đáp án:** Không. Tìm class-file resource và JVM class loading là hai cơ chế khác về ý nghĩa; custom loaders và module rules có thể xử lý khác.

**Câu 10.** ClassLoader.getResource có tìm một file bất kỳ tương đối với CWD không?

**Đáp án:** Không. Nó tra các resource roots của loader; CWD chỉ có thể tác động gián tiếp tới cách các relative classpath entries được diễn giải khi chương trình khởi chạy.

## 17. Ghi nhớ

**Công thức thực hành quan trọng nhất:**

~~~text
ClassLoader.getResource("dir/file.txt")
     → dir/file.txt từ gốc resource search của loader

SomeClass.class.getResource("file.txt")
     → package/of/SomeClass/file.txt

SomeClass.class.getResource("/dir/file.txt")
     → dir/file.txt từ gốc (Class bỏ slash đầu)
~~~

- Resource name dùng **/**, không dùng OS path.
- **Classpath root** có thể là thư mục, JAR hoặc nguồn do custom loader cung cấp.
- URL có thể là **file:**, **jar:**, **jrt:** hoặc dạng khác; ưu tiên **openStream** thay vì giả định File.
- **getResourceAsStream** phù hợp việc đọc resource; luôn kiểm tra null và đóng stream.
- Parent-first delegation có thể quyết định URL được trả về; **getResources** giúp điều tra tên trùng.
- Trong **named modules**, resource encapsulation có thể ảnh hưởng lookup.
- Tài nguyên trên filesystem bên ngoài artifact là câu chuyện khác; dùng **Files/Path** khi đúng nhu cầu.
- Một resource tìm thấy không chứng minh lớp tương ứng đã được JVM load hoặc initialize.

### Tài liệu chuẩn

- **ClassLoader Java SE 21 API** – getResource, getResources, findResource, getResourceAsStream: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **Class Java SE 21 API** – getResource và quy tắc tên relative/absolute: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- **Module Java SE 21 API** – getResourceAsStream và module encapsulation: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- **java Command Java SE 21** – -classpath và module/class loading: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
