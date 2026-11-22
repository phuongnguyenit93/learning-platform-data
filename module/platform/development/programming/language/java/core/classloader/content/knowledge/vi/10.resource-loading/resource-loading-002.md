# Class.getResource: đường dẫn tương đối và dấu / ở đầu

## 1. Bản chất của Class.getResource

Trong Java, *resource* là tệp dữ liệu dùng lúc chạy: cấu hình, template, thông báo, ảnh, chứng chỉ, v.v. Resource có thể ở một thư mục trên classpath, trong JAR hoặc trong một named module. Để tìm resource dựa trên một lớp, Java có:

~~~java
URL url = SomeClass.class.getResource("config.properties");
InputStream in = SomeClass.class.getResourceAsStream("config.properties");
~~~

`getResource` trả về `java.net.URL`, còn `getResourceAsStream` trả `InputStream`; cả hai có thể trả `null` khi tài nguyên không được tìm thấy hoặc không thể truy cập. Hai API **dùng chung quy tắc diễn giải tên đường dẫn**.

Điểm quan trọng nhất: **dấu `/` ở đầu chuỗi tên resource quyết định điểm bắt đầu tìm kiếm**.

- **Không có `/` đầu:** đường dẫn tương đối với **package của đối tượng `Class` gọi phương thức**.
- **Có `/` đầu:** đường dẫn tuyệt đối từ **gốc không gian tên resource**. API bỏ dấu `/` đầu khi chuyển tên cho cơ chế tìm kiếm bên dưới.
- Dấu `/` là dấu phân cách tên resource bất kể hệ điều hành; nó **không phải** đường dẫn gốc ổ đĩa hay filesystem.
- Không phải source file đang nằm ở đâu hoặc working directory là yếu tố quyết định tên tương đối. Quan trọng là **package của class được chọn** và **vị trí resource tại runtime**.

Ví dụ, class `com.acme.orders.OrderService` và resource `com/acme/orders/config.properties` thuộc cùng package resource. Câu lệnh `OrderService.class.getResource("config.properties")` chỉ định chính file đó; nếu thêm dấu `/` mà không thêm package thì lại yêu cầu resource **khác** ở root.

## 2. Thuật toán chuẩn hóa tên đường dẫn

Tài liệu `Class.getResource(String)` quy định cách chuyển tên resource sang tên tuyệt đối:

1. Nếu `name` bắt đầu bằng dấu `/`, bỏ dấu `/` đầu và dùng phần còn lại.
2. Nếu không, lấy package của class đang được tham chiếu, đổi dấu `.` thành `/`, ghép thêm `/` và chuỗi `name`.

Với `package com.acme.orders;`:

| Lời gọi | Tên tuyệt đối được tra cứu | Giải thích |
| --- | --- | --- |
| `getResource("config.properties")` | `com/acme/orders/config.properties` | Tương đối package |
| `getResource("/config.properties")` | `config.properties` | Root resource |
| `getResource("/com/acme/orders/config.properties")` | `com/acme/orders/config.properties` | Cùng tên như dòng 1 |
| `getResource("templates/mail.txt")` | `com/acme/orders/templates/mail.txt` | Thư mục con package |
| `getResource("/templates/mail.txt")` | `templates/mail.txt` | Thư mục con root |
| `getResource("com/acme/orders/config.properties")` | `com/acme/orders/com/acme/orders/config.properties` | Sai thường gặp: nhân đôi package |

Đây là **tên được yêu cầu tìm**, không đảm bảo tìm được. Muốn biết có tồn tại, phải xét classpath/JAR/module, class loader và quyền truy cập.

Hình dung classpath root là `out/classes`:

~~~text
out/classes/
├── root.txt
└── com/
    └── acme/
        └── orders/
            ├── OrderService.class
            ├── config.properties
            └── templates/
                └── mail.txt
~~~

Những lời gọi sau có kết quả dự kiến nếu chỉ có các resource nêu trong cây:

~~~java
OrderService.class.getResource("config.properties");  // FOUND
OrderService.class.getResource("/com/acme/orders/config.properties"); // FOUND
OrderService.class.getResource("/config.properties"); // NOT_FOUND
OrderService.class.getResource("/root.txt");           // FOUND
OrderService.class.getResource("root.txt");            // NOT_FOUND
OrderService.class.getResource("templates/mail.txt");  // FOUND
~~~

Đoạn này chỉ minh họa biểu thức, không phải chương trình biên dịch độc lập; hãy xét chúng như các lệnh nằm trong một phương thức hợp lệ. Trong ứng dụng nhiều JAR, tên bị đánh dấu NOT_FOUND vẫn có thể có bản ở entry khác, nên phải kiểm tra classpath runtime thực tế.

## 3. Phân biệt Class.getResource với ClassLoader.getResource

Cùng tên `getResource` nhưng **quy tắc đường dẫn không giống nhau**:

| API | Có tự thêm package? | Dấu `/` ở đầu |
| --- | --- | --- |
| `SomeClass.class.getResource(name)` | Có, khi tên không bắt đầu bằng `/` | Có ý nghĩa tuyệt đối; Java loại bỏ ký tự đó |
| `SomeClass.class.getResourceAsStream(name)` | Có, tương tự `Class.getResource` | Cùng quy tắc |
| `someLoader.getResource(name)` | Không | Truyền tên từ gốc, thông thường **không thêm** dấu `/` |
| `someLoader.getResourceAsStream(name)` | Không | Dùng tên từ gốc |
| `ClassLoader.getSystemResource(name)` | Không | Dùng tên từ gốc |

Ví dụ tên thật của resource là `com/acme/orders/config.properties`:

~~~java
URL a = OrderService.class.getResource("config.properties");
URL b = OrderService.class.getResource(
        "/com/acme/orders/config.properties");

ClassLoader loader = OrderService.class.getClassLoader();
URL c = loader.getResource("com/acme/orders/config.properties");
~~~

Cả ba biểu thức tìm cùng **tên logic** trong tình huống classpath/loader thông dụng, nhưng không phải lúc nào chúng cũng bắt buộc trả cùng resource trong môi trường named module hoặc custom loader. Đoạn trên giả định `OrderService` và `loader` tồn tại, và loader khác `null`.

**Lỗi phổ biến:** `loader.getResource("/com/acme/orders/config.properties")`. Không có bước “bỏ slash đầu” trong hợp đồng `ClassLoader.getResource`; loader tích hợp thường không tìm thấy và trả `null`. Cách dùng portable là bỏ dấu `/` trước tên truyền cho `ClassLoader`.

**Cảnh báo bootstrap:** `String.class.getClassLoader()` thường bằng `null`, nên gọi tiếp `.getResource(...)` sẽ gây `NullPointerException`. Với Class của kiểu bootstrap, dùng trực tiếp API `Class.getResource` hoặc API phù hợp với resource mong tìm; đừng giả định có một đối tượng loader Java để gọi.

## 4. Bài thực hành Java 17+: thư mục package và root

Tạo hai nhóm file: Java source và ba text resources.

~~~text
example/
├── src/
│   └── demo/
│       └── ResourceDemo.java
└── resources/
    ├── global.txt
    └── demo/
        ├── config.properties
        └── assets/
            └── help.txt
~~~

Nội dung `resources/demo/config.properties` là `ENV=training`, `resources/global.txt` là `ROOT`, và `resources/demo/assets/help.txt` là `HELP`. Mỗi file có một dòng text thông thường.

### File src/demo/ResourceDemo.java

~~~java
package demo;

import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class ResourceDemo {
    private static void check(String name, URL url) {
        System.out.println(name + " -> "
                + (url != null ? "FOUND" : "NOT_FOUND"));
    }

    public static void main(String[] args) throws Exception {
        check("relative same-package",
                ResourceDemo.class.getResource("config.properties"));
        check("absolute same-package",
                ResourceDemo.class.getResource("/demo/config.properties"));
        check("relative root",
                ResourceDemo.class.getResource("global.txt"));
        check("absolute root",
                ResourceDemo.class.getResource("/global.txt"));
        check("wrong root",
                ResourceDemo.class.getResource("/config.properties"));
        check("relative subfolder",
                ResourceDemo.class.getResource("assets/help.txt"));

        check("loader root-path",
                ResourceDemo.class.getClassLoader()
                        .getResource("demo/config.properties"));
        check("loader leading-slash",
                ResourceDemo.class.getClassLoader()
                        .getResource("/demo/config.properties"));

        try (InputStream in = ResourceDemo.class
                .getResourceAsStream("config.properties")) {
            if (in == null) {
                throw new IllegalStateException("config missing");
            }
            String content = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println("contents -> " + content);
        }
    }
}
~~~

`ResourceDemo` thuộc package `demo`, nên tên tương đối `config.properties` được đổi thành `demo/config.properties`. Trong khi đó, `/global.txt` chỉ định root resource. Ví dụ cũng cố ý dùng cách gọi ClassLoader với và không với dấu slash để thấy hai API khác nhau.

### Biên dịch và chạy trên Linux/macOS

Đứng trong thư mục `example`:

~~~bash
mkdir -p out/demo/assets
javac -d out src/demo/ResourceDemo.java
cp resources/demo/config.properties out/demo/config.properties
cp resources/demo/assets/help.txt out/demo/assets/help.txt
cp resources/global.txt out/global.txt
java -cp out demo.ResourceDemo
~~~

### Biên dịch và chạy trên Windows PowerShell

Đứng trong thư mục `example`:

~~~powershell
New-Item -ItemType Directory -Force out\demo\assets | Out-Null
javac -d out src\demo\ResourceDemo.java
Copy-Item resources\demo\config.properties out\demo\config.properties
Copy-Item resources\demo\assets\help.txt out\demo\assets\help.txt
Copy-Item resources\global.txt out\global.txt
java -cp out demo.ResourceDemo
~~~

Phải **copy cả resources**, vì `javac -d out ...` không tự copy tệp `.properties`/`.txt`.

Kết quả stdout khi chạy với các resource đã đặt đúng vị trí:

~~~text
relative same-package -> FOUND
absolute same-package -> FOUND
relative root -> NOT_FOUND
absolute root -> FOUND
wrong root -> NOT_FOUND
relative subfolder -> FOUND
loader root-path -> FOUND
loader leading-slash -> NOT_FOUND
contents -> ENV=training
~~~

Kết quả trên đã được kiểm chứng bằng `javac`/`java` trên JDK thực. Dòng `loader leading-slash -> NOT_FOUND` phản ánh application/system loader chuẩn được dùng trong thí nghiệm; đừng coi việc một custom loader nhận dấu slash đầu là hợp đồng được đảm bảo.

### Đóng gói resource trong JAR

Khi thư mục `out` chứa `demo/ResourceDemo.class` và các resource ở đúng đường dẫn, chạy:

~~~bash
jar --create --file resources-demo.jar -C out .
java -cp resources-demo.jar demo.ResourceDemo
~~~

Các lệnh này cũng áp dụng trong Windows PowerShell với JDK 17+. **Đầu ra y hệt** phiên bản chạy từ folder, và đã được kiểm chứng bằng một JAR chứa cả class lẫn resource. Đây là lý do nên đọc resource bằng Java resource API thay vì hardcode đường dẫn filesystem.

## 5. Đường dẫn tương đối gắn với Class nào?

Giả sử có hai lớp ở hai package:

~~~java
package alpha;
public class A {}
~~~

~~~java
package beta;
public class B {}
~~~

Hai đoạn trên là **hai file Java riêng**. Lời gọi `A.class.getResource("data.txt")` tìm `alpha/data.txt`, còn `B.class.getResource("data.txt")` tìm `beta/data.txt`.

Ngay cả khi lời gọi `A.class.getResource("data.txt")` được viết và thực thi bởi code trong `beta.B`, base của resource vẫn là package `alpha`. Điều cần nhìn là **đối tượng Class** phía trước `.getResource`, không phải package của caller hoặc tên thư mục nơi process đang chạy.

Với nested class, package base cũng là package của kiểu đó, không tự thêm tên nested class. Với lớp thuộc default package, tên tương đối không có package prefix. Trong code ứng dụng, nên dùng package rõ ràng để tránh ambiguity khi đóng gói.

Một chiến lược ổn định cho thư viện là dùng `MyLibraryClass.class.getResource("library-config.json")` khi resource nằm cạnh class của thư viện, hoặc dùng đường dẫn root `"/com/vendor/library-config.json"` nếu cần chỉ định tên rõ ràng, tránh vô tình đọc resource khác cùng tên.

## 6. Đọc dữ liệu: URL, InputStream, encoding và null

`Class.getResource` trả `URL`, thích hợp khi API nhận URL hoặc khi muốn mở bằng `url.openStream()`. `Class.getResourceAsStream` trả stream trực tiếp. Cả hai có thể trả `null`; không nên gọi `url.openStream()` khi chưa kiểm tra.

Một mẫu đọc bytes an toàn:

~~~java
try (InputStream in = MyClass.class
        .getResourceAsStream("/config/app.json")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource not found: /config/app.json");
    }
    String json = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
    // Xử lý json bằng parser JSON phù hợp.
}
~~~

Đây là **đoạn mã minh họa bên trong phương thức**, giả định đã import `InputStream` và `StandardCharsets`, đồng thời file tồn tại. `readAllBytes` phù hợp với resource nhỏ; với dữ liệu lớn nên đọc theo từng chunk. *Try-with-resources* đóng stream cả khi xử lý có exception.

Đừng mặc định API `Properties.load(InputStream)` diễn giải text UTF-8 như `new String(..., UTF_8)`: nó có quy tắc encoding truyền thống riêng. Nếu resource là properties UTF-8, hãy xem xét `Properties.load(Reader)` với reader được cấu hình encoding phù hợp.

**Không convert URL resource thành File một cách mù quáng:**

~~~java
URL url = MyClass.class.getResource("/config/app.json");
File file = new File(url.getFile()); // không đáng tin khi chạy từ JAR
~~~

Đây là **phản ví dụ**, không phải khuyến nghị. Bên trong JAR, URL có thể là `jar:file:...!/config/app.json`; entry không phải một file độc lập trên ổ đĩa. Dùng stream hoặc API xử lý archive/URL thích hợp, và chỉ trích xuất ra file tạm khi API khác thật sự bắt buộc cần filesystem path.

## 7. Vị trí runtime không phải vị trí thư mục source

Với Maven/Gradle Java layout phổ biến:

~~~text
src/
└── main/
    ├── java/com/acme/app/Main.java
    └── resources/
        ├── global.properties
        └── com/acme/app/banner.txt
~~~

Thông thường build tool copy nội dung dưới `src/main/resources` vào **root output resource** rồi đóng gói cùng class. Khi đó `Main.class.getResource("banner.txt")` tìm `com/acme/app/banner.txt`; `Main.class.getResource("/global.properties")` tìm resource gốc. Không viết tên `"src/main/resources/global.properties"`, vì prefix nguồn đó **không còn là một phần tên resource runtime**.

Nếu chạy trực tiếp bằng `javac` và `java`, chỉ build source sẽ không tự bảo đảm resource được copy. Nếu chạy từ IDE mà tìm được còn JAR thì không, kiểm tra quy trình đóng gói. Có thể dùng `jar tf app.jar` để xem entry thực tế (tên entry được phân cách bằng dấu `/`).

**Đặc tính cần nhớ:** `getResource("config.txt")` không dựa trên current working directory. Đổi `user.dir` không làm package base thay đổi; nhưng nếu bạn chạy với classpath **tương đối** rồi đổi working directory trước khi khởi chạy JVM, classpath entry có thể chỉ tới nơi khác.

## 8. JAR, named module và custom loader: trường hợp đặc biệt

### JAR

Resource được đặt trong JAR theo tên entry như `demo/config.properties`. Quy tắc dấu `/` đầu của `Class.getResource` vẫn dựa trên **tên logic**; chỉ cơ chế mở dữ liệu vật lý đổi từ file sang JAR. Nếu resource chỉ nằm trong source tree mà không được đóng gói vào JAR, API không tự tìm lại source tree.

### Named module (Java 9+)

Với lớp trong **named module**, `Class.getResource`/`getResourceAsStream` tìm trong module của lớp, và truy cập resource còn chịu **encapsulation** của module. Đặc biệt, resource không phải `.class` nằm trong package không được mở tới module đang gọi có thể không truy cập được dù tên và file đều đúng.

Dấu `/` đầu **không vượt qua quyền mở package**. Nếu đường dẫn sau chuẩn hóa đã đúng mà kết quả `null`, kiểm tra `module-info.java` và quy tắc `opens`, không chỉ thử thêm/bỏ slash.

`ClassLoader.getResource` với named module cũng có quy tắc riêng, trong đó tài nguyên không phải `.class` trong package named module thường phải nằm ở package **opened unconditionally** để API `ClassLoader` công khai có thể tìm. Do đó không khẳng định hai API `Class.getResource` và `ClassLoader.getResource` luôn hoàn toàn tương đương khi làm việc với named modules.

### Custom class loader

Với lớp ở unnamed module, `Class.getResource` sử dụng defining loader của đối tượng class được chọn để tìm tài nguyên sau bước chuẩn hóa tên. Một plugin được nạp từ custom child loader có thể nhìn thấy resource riêng của plugin, còn một class của parent có thể không thấy file đó.

Mặc định `ClassLoader.getResource` thường thử parent trước rồi mới `findResource` trong loader hiện tại, nhưng loader tùy biến có thể có chính sách khác. Nếu nhiều JAR có resource cùng tên, kết quả còn phụ thuộc loader và thứ tự tìm. Đây là lý do nên chọn đối tượng `Class` đại diện đúng thành phần sở hữu resource.

Thread context class loader chỉ liên quan nếu ứng dụng/framework **chủ động** dùng nó; nó không tự trở thành base cho mọi lời gọi `SomeClass.class.getResource`.

## 9. Chẩn đoán trường hợp getResource trả null

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `MyClass.class.getResource("config.yml") == null` | File ở root, nhưng tên tương đối đang tìm trong package. | Dùng `"/config.yml"` hoặc đặt file dưới package. |
| `MyClass.class.getResource("/pkg/config.yml") == null` | Resource chưa copy vào output/JAR, sai tên, sai chữ hoa/thường. | Xem cây output, dùng `jar tf` kiểm tra entry. |
| Gọi `getResource("pkg/config.yml")` trong class package `pkg` | Bị nhân đôi prefix package: `pkg/pkg/config.yml`. | Dùng `"config.yml"` hoặc `"/pkg/config.yml"`. |
| `loader.getResource("/pkg/config.yml") == null` | Dùng sai quy tắc dấu `/` đầu của `ClassLoader`. | Dùng `loader.getResource("pkg/config.yml")`. |
| Chạy folder được, JAR lỗi | Resource không được đóng gói hoặc code ép URL thành File. | Đóng gói resource, đọc qua InputStream. |
| Trong named module có file mà vẫn null | Package resource bị encapsulated. | Kiểm tra `opens` và caller module. |
| Chỉ fail khi chuyển Windows sang Linux | Sai chữ hoa/thường tên entry, dùng `\` cho resource. | Dùng tên chính xác và dấu `/`. |
| Có nhiều class loader | Lớp được chọn cho lookup do loader không thấy resource định nghĩa. | Kiểm tra `clazz.getClassLoader()` và nguồn resource thực. |

Không dùng mỗi `System.out.println(getResource(...))` rồi hardcode chuỗi URL tuyệt đối vào test. URL có thể chứa thư mục tạm, prefix `file:`, `jar:` hoặc encoding khác nhau theo môi trường. Test nên kiểm tra **tồn tại** và **nội dung** dữ liệu.

## 10. Checklist và câu hỏi ôn tập

Trước khi gọi API, xác định: **(1)** package của class được dùng; **(2)** tên entry resource tại runtime; **(3)** muốn tìm tương đối hay từ root; **(4)** dùng `Class` hay `ClassLoader`; **(5)** class loader/module nào cung cấp resource; **(6)** tài nguyên có nằm trong JAR không; **(7)** đã kiểm tra null, đóng stream và chỉ định encoding chưa.

**Câu 1.** Class `org.demo.Widget` cần đọc `org/demo/config.xml`. Hai tên resource nào đưa vào `Widget.class.getResource` là tương đương?

**Đáp:** `"config.xml"` và `"/org/demo/config.xml"`: đều chuẩn hóa thành `org/demo/config.xml`.

**Câu 2.** File `global.txt` nằm tại root classpath. Vì sao `Widget.class.getResource("global.txt")` thường không tìm thấy?

**Đáp:** Nó tìm `org/demo/global.txt`. Dùng `Widget.class.getResource("/global.txt")` để yêu cầu tên root.

**Câu 3.** Có nên thêm dấu slash đầu khi đổi từ `Widget.class.getResource("/org/demo/config.xml")` sang `Widget.class.getClassLoader().getResource(...)` không?

**Đáp:** Không. ClassLoader nhận `"org/demo/config.xml"`, không tự bỏ slash đầu; còn phải xử lý nếu class loader bằng `null`.

**Câu 4.** Đổi folder sang JAR có làm quy tắc dấu slash đầu của `Class.getResource` thay đổi?

**Đáp:** Không. Tên logic vẫn vậy; chỉ cách lưu trữ/mở resource đổi, nên thường đọc bằng stream thay vì ép URL thành file vật lý.

## Tài liệu chuẩn

- [Class.getResource(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): tên tương đối và chuẩn hóa slash đầu.
- [Class.getResourceAsStream(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)): quy tắc tra cứu và trả InputStream.
- [ClassLoader.getResource(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getResource(java.lang.String)): tên slash-separated từ gốc và parent delegation.
- [Module.getResourceAsStream(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): tài nguyên thuộc named modules và quyền truy cập.
