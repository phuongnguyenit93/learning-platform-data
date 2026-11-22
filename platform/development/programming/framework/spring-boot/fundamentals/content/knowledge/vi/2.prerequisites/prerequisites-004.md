# Package, classpath, JAR và cách Java tìm lớp

Trong Spring Boot, một lớp có thể biên dịch bình thường nhưng khi chạy lại xuất hiện lỗi `ClassNotFoundException`, `NoClassDefFoundError` hoặc `Could not find or load main class`. Muốn hiểu các lỗi này, trước hết cần phân biệt **tên đầy đủ của lớp**, **vị trí chứa bytecode**, **cách đóng gói JAR** và **cơ chế JVM nạp lớp**.

Bài học thuộc phần **Kiến thức chuẩn bị** của **Spring Boot Fundamentals**. Các khái niệm được giải thích từ Java thuần, sau đó nối với cấu trúc dự án Spring Boot.

## 1. Từ tệp `.java` đến lớp được JVM sử dụng

Một chương trình Java thường đi qua hai thời điểm khác nhau:

```text
Mã nguồn (.java)
    │
    ▼
javac — biên dịch; cần tìm các kiểu dữ liệu mà mã nguồn tham chiếu
    │
    ▼
Bytecode (.class)
    │
    ├── nằm trong thư mục classes/
    └── hoặc được đóng gói trong JAR
                │
                ▼
java — khởi chạy JVM
                │
                ▼
Class loader tìm và nạp các lớp cần dùng
                │
                ▼
JVM liên kết, khởi tạo lớp khi cần và thực thi bytecode
```

Ba câu hỏi cần tách biệt:

- **Lớp tên gì?** Tên `package` kết hợp với tên lớp tạo thành tên đủ điều kiện (*fully qualified class name*).
- **Lớp nằm ở đâu?** `classpath` hoặc cơ chế nạp lớp tương ứng chỉ ra vị trí có thể tìm thấy mã đã biên dịch.
- **Lớp được phân phối thế nào?** JAR gom các tệp `.class` và tài nguyên vào một kho lưu trữ; cấu trúc JAR quyết định cách chương trình được khởi chạy.

Một tệp `.java` không phải là thứ JVM thường tìm để thực thi. JVM cần định nghĩa lớp đã biên dịch hoặc được cung cấp bởi runtime.

## 2. `package`: định danh và tổ chức lớp

### 2.1. Tên ngắn và tên đầy đủ

Xét lớp:

```java
package com.example.catalog;

public class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

- Tên ngắn: `Product`.
- Package: `com.example.catalog`.
- Tên đầy đủ: `com.example.catalog.Product`.

Hai lớp có tên ngắn giống nhau vẫn có thể cùng tồn tại nếu thuộc hai package khác nhau, chẳng hạn `com.example.catalog.Product` và `com.example.billing.Product`.

Khai báo `package` thường nằm đầu tệp nguồn, trước các lệnh `import`. Quy ước Java dùng chữ thường cho package và tên miền đảo ngược để giảm nguy cơ trùng tên.

### 2.2. `package` và đường dẫn thư mục

Với dự án Maven hoặc Gradle thông thường, cách tổ chức nguồn nên phản ánh package:

```text
src/main/java/
└── com/
    └── example/
        └── catalog/
            └── Product.java
```

Sau khi biên dịch với thư mục đích `out`, lớp sẽ có dạng:

```text
out/
└── com/
    └── example/
        └── catalog/
            └── Product.class
```

Ở đây, `out` là **gốc classpath**, còn `com/example/catalog/Product.class` là đường dẫn tương ứng với tên lớp. Dùng dấu `.` trong tên package và dấu phân cách thư mục trong đường dẫn tệp là hai cách biểu diễn cùng một cấu trúc logic.

Cần phân biệt: khai báo `package` quyết định tên lớp; vị trí tệp nguồn theo package là quy ước quan trọng của công cụ build và IDE. Trình biên dịch có thể nhận tệp nguồn từ một đường dẫn khác nếu được chỉ định rõ, nhưng việc giữ đúng cấu trúc sẽ giúp công cụ tìm nguồn và tài nguyên ổn định.

### 2.3. `import` làm gì, và không làm gì?

Ví dụ trong một package khác:

```java
package com.example.checkout;

import com.example.catalog.Product;

public class CheckoutService {
    public String label(Product product) {
        return product.getName();
    }
}
```

`import` cho phép viết `Product` thay cho `com.example.catalog.Product` trong mã nguồn. Nó **không** tự tải thư viện, không sao chép lớp và không bổ sung gì vào classpath.

Nếu `Product.class` hoặc thư viện chứa nó không có trong đầu vào biên dịch, `import` vẫn không giúp `javac` tìm thấy lớp. Nếu lúc biên dịch có lớp nhưng lúc chạy thiếu, chương trình vẫn có thể lỗi khi JVM cần đến lớp đó.

Lớp trong `java.lang` được nhập ngầm định; các lớp khác thường cần `import` hoặc tên đầy đủ. Hạn chế dùng *unnamed/default package* trong dự án thực tế, đặc biệt với ứng dụng Spring Boot.

## 3. `classpath`: tập vị trí để tìm lớp và tài nguyên

**Classpath** là danh sách các thư mục chứa bytecode và các tệp JAR mà công cụ Java có thể dùng để tìm lớp, cùng tài nguyên đi kèm. Nó không phải một package và cũng không phải một thư mục duy nhất.

Ví dụ:

```text
out/                     # thư mục gốc chứa các .class
libs/common-utils.jar    # thư viện đã đóng gói
libs/json-support.jar
```

Khi một class loader tìm `com.example.catalog.Product` trong thư mục `out`, đường dẫn tương ứng là:

```text
out/com/example/catalog/Product.class
```

Nếu tìm trong JAR, nó tra một mục có tên:

```text
com/example/catalog/Product.class
```

Classpath phải trỏ đến **gốc** chứa cấu trúc package, không trỏ thẳng vào thư mục `.../catalog` chỉ vì lớp nằm trong đó.

### 3.1. Classpath khi biên dịch và khi chạy

Hai lệnh sau phục vụ hai giai đoạn riêng biệt:

```bash
javac -cp "libs/common-utils.jar" -d out src/com/example/app/Main.java
java -cp "out:libs/common-utils.jar" com.example.app.Main
```

- `javac -cp`: nơi trình biên dịch tìm các kiểu đã được biên dịch mà mã nguồn sử dụng.
- `java -cp`: nơi bộ nạp lớp của ứng dụng tìm các lớp khi chạy.
- `javac -d out`: nơi trình biên dịch ghi tệp `.class`; `-d` **không** tự động làm `out` trở thành classpath của một lệnh `java` về sau.
- `com.example.app.Main`: tên đầy đủ của lớp có điểm vào `main`.

Ví dụ trên dùng dấu phân cách classpath của Linux/macOS. Trên Windows, dùng dấu `;`:

```powershell
java -cp "out;libs/common-utils.jar" com.example.app.Main
```

Dấu `:` hay `;` dùng để **ngăn cách các mục classpath**, khác với dấu chấm phân cách các phần trong tên package.

Trong những lệnh đơn giản, `-cp` và `-classpath` tương đương. Tùy cách khởi chạy, có thể dùng biến môi trường `CLASSPATH`, nhưng khai báo `-cp` ngay trong lệnh giúp thấy rõ phụ thuộc. Nếu truyền `-cp`, giá trị đó thay cho biến `CLASSPATH` đối với lệnh ấy.

### 3.2. Thư mục thư viện và wildcard

Có thể chỉ định các JAR trực tiếp trong một thư mục:

```bash
# Linux/macOS
java -cp "out:libs/*" com.example.app.Main
```

```powershell
# Windows PowerShell
java -cp "out;libs/*" com.example.app.Main
```

`libs/*` được Java launcher mở rộng thành các JAR trong thư mục đó; nó không tìm đệ quy mọi thư mục con. Bọc classpath trong dấu nháy giúp tránh shell tự xử lý ký tự đặc biệt theo cách không mong muốn.

Classpath thông thường dành cho lớp ứng dụng và thư viện bên ngoài; các lớp chuẩn như `java.lang.String` đến từ các module của Java runtime, không cần thêm tệp JAR của JDK vào classpath.

## 4. Thực hành Java thuần: biên dịch, chạy và đóng gói JAR

Để quan sát đúng mối liên hệ giữa package, tên lớp và classpath, tạo hai tệp nguồn sau:

```text
sample/
└── src/
    └── com/
        └── example/
            └── lesson/
                ├── Main.java
                └── Greeting.java
```

`src/com/example/lesson/Greeting.java`:

```java
package com.example.lesson;

public class Greeting {
    public static String message() {
        return "Xin chào từ Java!";
    }
}
```

`src/com/example/lesson/Main.java`:

```java
package com.example.lesson;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Từ thư mục `sample`, chạy:

```bash
javac -d out src/com/example/lesson/Greeting.java src/com/example/lesson/Main.java
java -cp out com.example.lesson.Main
```

Kết quả:

```text
Xin chào từ Java!
```

Sau biên dịch, cấu trúc chính là:

```text
out/
└── com/
    └── example/
        └── lesson/
            ├── Greeting.class
            └── Main.class
```

Tại sao không chạy `java -cp out Main`? Vì lớp không mang tên `Main` trong unnamed package; tên thực tế là `com.example.lesson.Main`. Tương tự, `java -cp out/com/example/lesson com.example.lesson.Main` đặt sai gốc để tìm tên lớp đầy đủ.

### 4.1. Tạo JAR thông thường

JAR (*Java ARchive*) là định dạng lưu trữ dựa trên ZIP, có thể chứa bytecode, tài nguyên và metadata.

Tiếp tục trong thư mục `sample`:

```bash
jar --create --file lesson.jar --main-class com.example.lesson.Main -C out .
jar --list --file lesson.jar
java -jar lesson.jar
```

Tùy JDK, danh sách mục sẽ bao gồm các đường dẫn tương tự:

```text
META-INF/
META-INF/MANIFEST.MF
com/example/lesson/Greeting.class
com/example/lesson/Main.class
```

`-C out .` yêu cầu công cụ `jar` lấy nội dung **bên trong** `out` làm gốc của JAR. Nhờ vậy, trong kho lưu trữ có mục `com/example/lesson/Main.class` chứ không có tiền tố `out/`.

Tùy chọn `--main-class` ghi tên điểm vào vào `META-INF/MANIFEST.MF`. Manifest có thể chứa dòng:

```text
Main-Class: com.example.lesson.Main
```

Vì thế `java -jar lesson.jar` biết phải chạy lớp nào. Một JAR **không bắt buộc** có `Main-Class` nếu chỉ được dùng làm thư viện.

Với JAR ví dụ, cũng có thể chạy:

```bash
java -cp lesson.jar com.example.lesson.Main
```

Cách này chỉ định trực tiếp lớp `main`, không cần dựa vào `Main-Class` trong manifest.

### 4.2. Khi JAR phụ thuộc vào thư viện ngoài

Giả sử `Main` dùng một lớp nằm trong `libs/parser.jar`. Một JAR thông thường chỉ chứa các tệp đã được đưa vào khi đóng gói, **không mặc nhiên nhúng mọi thư viện phụ thuộc**.

Nếu chạy bằng classpath:

```bash
# Linux/macOS
java -cp "lesson.jar:libs/*" com.example.lesson.Main
```

```powershell
# Windows
java -cp "lesson.jar;libs/*" com.example.lesson.Main
```

Nếu chạy `java -jar lesson.jar`, tùy chọn `-cp` ở lệnh khởi chạy không được dùng làm user classpath cho ứng dụng. Với JAR thông thường, muốn `java -jar` tìm thư viện ngoài có thể khai báo các đường dẫn thích hợp trong thuộc tính `Class-Path` của manifest hoặc dùng cách phân phối/khởi chạy khác. Danh sách `Class-Path` trong manifest trỏ đến JAR/thư mục riêng bên ngoài, không biến JAR lồng bên trong thành phần tử classpath thông thường.

Điểm mấu chốt: **đóng gói được lớp chính** không đồng nghĩa với **đóng gói đủ mọi phụ thuộc chạy thực tế**.

## 5. JVM tìm lớp qua class loader như thế nào?

### 5.1. Từ tên lớp đến bytecode

Khi ứng dụng cần dùng `com.example.lesson.Greeting`, một class loader có thể tìm định nghĩa lớp qua một mục tương ứng với `com/example/lesson/Greeting.class`. Nếu có nhiều thư mục/JAR trên classpath, vị trí và thứ tự tra cứu ảnh hưởng đến định nghĩa nào được chọn.

Mô hình đơn giản:

```text
java -cp "out:libs/*" com.example.lesson.Main
       │
       ▼
Application class loader
       │
       ├── được yêu cầu nạp com.example.lesson.Main
       ├── tìm nguồn định nghĩa .class thích hợp
       ├── Main gọi Greeting.message()
       └── khi cần, nạp com.example.lesson.Greeting
                       │
                       ▼
                    thực thi
```

Class loading không đồng nghĩa với việc JVM quét và nạp toàn bộ mọi lớp có sẵn ngay khi khởi động. Nhiều lớp chỉ được nạp, liên kết hoặc khởi tạo khi có nhu cầu sử dụng; chi tiết thời điểm phụ thuộc quy tắc của JVM và cách chương trình tham chiếu lớp.

### 5.2. Các bộ nạp lớp thường gặp

Java hiện đại thường có những tầng sau:

| Bộ nạp lớp | Vai trò khái quát |
|---|---|
| Bootstrap class loader | Nạp các lớp nền tảng quan trọng của Java runtime. |
| Platform class loader | Nạp các lớp thuộc các module nền tảng không do bootstrap trực tiếp xử lý. |
| Application/System class loader | Nạp lớp ứng dụng từ classpath khi dùng cách khởi chạy thông thường. |
| Custom class loader | Do framework, máy chủ ứng dụng hoặc công cụ tạo để hỗ trợ chiến lược nạp lớp riêng. |

Phần lớn class loader Java sử dụng nguyên tắc **ủy quyền cho loader cha trước** (*parent delegation*). Điều này giúp chia sẻ các lớp nền tảng và hạn chế một lớp ứng dụng vô tình thay thế lớp lõi của Java. Một số framework có cơ chế riêng, nên không được suy diễn rằng mọi loader luôn có cùng quy tắc tìm kiếm.

Chu trình liên quan đến một lớp gồm các pha như **loading**, **linking** (kiểm tra, chuẩn bị và giải quyết tham chiếu) và **initialization**. Ví dụ, khối `static` có thể chạy khi lớp được khởi tạo, chứ không nhất thiết tại thời điểm JAR được mở.

### 5.3. Tìm lớp trực tiếp và tìm lớp bằng tên ở runtime

Các tham chiếu kiểu rõ ràng:

```java
Greeting.message();
```

khác với tra cứu bằng chuỗi:

```java
Class<?> type = Class.forName("com.example.lesson.Greeting");
System.out.println(type.getName());
```

Trong trường hợp thứ hai, tên lớp được quyết định lúc chạy. Nếu loader phù hợp không tìm thấy định nghĩa lớp, `Class.forName` có thể ném `ClassNotFoundException`. Framework thường có những điểm tra cứu động tương tự khi xử lý cấu hình, plugin, tài nguyên hoặc annotation.

Kể cả khi lớp tồn tại, class loader không tự đăng ký lớp đó thành Spring bean. **Có lớp trên classpath** và **có bean trong Spring ApplicationContext** là hai điều kiện riêng.

### 5.4. Classpath và module path không phải một

Từ Java 9, Java Platform Module System (JPMS) cung cấp thêm **module path** qua `--module-path` và mô tả module bằng `module-info.java`. Module path bổ sung quy tắc đọc module, export package và kiểm soát phụ thuộc.

Bài này dùng mô hình **classpath** phổ biến của các ứng dụng Spring Boot. Khi gặp `--module-path` hay `module-info.java`, cần biết đó là cơ chế khác, không chỉ là tên mới của `-cp`.

## 6. Liên hệ với cấu trúc Spring Boot

Một ứng dụng Spring Boot thường có cấu trúc nguồn như sau:

```text
src/main/
├── java/
│   └── com/example/shop/
│       ├── ShopApplication.java
│       ├── controller/ProductController.java
│       └── service/ProductService.java
└── resources/
    ├── application.yml
    └── static/
```

`ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`ProductController`, `ProductService` có package riêng trong nhánh `com.example.shop`. Package không chỉ dùng để tìm bytecode; nó còn ảnh hưởng đến phạm vi quét component mặc định của Spring Boot: `@SpringBootApplication` thường kích hoạt quét package của lớp ứng dụng và các package con. Vì vậy, đặt lớp khởi động ở package gốc phù hợp thường là lựa chọn tốt.

Một lớp có mặt trong bytecode nhưng nằm ngoài vùng quét có thể không trở thành bean. Khi đó lỗi thiếu bean không nhất thiết là lỗi thiếu classpath.

### 6.1. Build tool quản lý classpath

Với Maven hoặc Gradle, bạn khai báo dependencies; build tool sẽ giải quyết thư viện, tổ chức classpath biên dịch và classpath chạy. Cấu trúc nguồn phổ biến là:

- `src/main/java`: mã Java ứng dụng.
- `src/main/resources`: cấu hình và tài nguyên được đưa vào runtime classpath.
- `src/test/java` và `src/test/resources`: mã và tài nguyên thử nghiệm, thường có classpath riêng.

Ví dụ `application.yml` thường được truy cập trên classpath nhờ việc đóng gói tài nguyên, chứ không phải nhờ khai báo package Java.

Trong một dự án Gradle có Spring Boot plugin, task `bootJar` tạo JAR thực thi; trong dự án Maven có Spring Boot Maven Plugin với bước `repackage`, artifact cũng có thể được đóng gói thành executable JAR. Tên tệp và vị trí đầu ra phụ thuộc cấu hình dự án (thường là `build/libs/` với Gradle và `target/` với Maven).

### 6.2. JAR thường và Spring Boot executable JAR

Một Spring Boot executable JAR theo cách đóng gói mặc định có cấu trúc đặc trưng:

```text
shop-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/shop/ShopApplication.class
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        └── các-thu-vien-khac.jar
```

Hai vị trí quan trọng:

- `BOOT-INF/classes/`: lớp và tài nguyên của ứng dụng.
- `BOOT-INF/lib/`: các JAR phụ thuộc được đóng gói bên trong.

Khác với JAR đơn giản ở phần trước, `java -jar shop-app.jar` không trực tiếp tìm `ShopApplication.class` ở gốc kho lưu trữ. Nó chạy **Spring Boot launcher** theo `Main-Class` của manifest. Launcher thiết lập cơ chế nạp lớp phù hợp để dùng cả `BOOT-INF/classes` và các JAR lồng trong `BOOT-INF/lib`, rồi gọi lớp ứng dụng được khai báo ở `Start-Class`.

Ví dụ các trường ý nghĩa trong manifest của Spring Boot 3.2+:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.shop.ShopApplication
```

Đây là ví dụ cho kiểu đóng gói dùng `JarLauncher`; tên launcher cụ thể có thể khác ở phiên bản Spring Boot hoặc kiểu đóng gói khác. Không nên tự sửa `Main-Class` sang `ShopApplication` rồi kỳ vọng cách nạp JAR lồng vẫn hoạt động.

Để quan sát archive đã build:

```bash
jar --list --file build/libs/shop-app.jar
java -jar build/libs/shop-app.jar
```

Các lệnh minh họa giả định artifact thực tế có tên `shop-app.jar`; cần thay bằng tên đúng mà dự án tạo ra.

**Vì sao không chạy `java -cp shop-app.jar com.example.shop.ShopApplication`?** Với executable JAR dạng này, lớp ứng dụng nằm dưới `BOOT-INF/classes/` thay vì ở gốc JAR, còn các phụ thuộc nằm dưới `BOOT-INF/lib/`. Classpath Java thông thường không tự coi những vị trí lồng đó là các gốc classpath. Cách khởi chạy dự kiến là `java -jar` hoặc cơ chế launch do build tool/framework cung cấp.

## 7. Những lỗi điển hình và nguyên nhân

| Biểu hiện | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `Could not find or load main class com.example.app.Main` | Sai tên đầy đủ của lớp chính, sai gốc classpath hoặc chưa biên dịch được `Main.class`. | Xem khai báo `package`, đường dẫn `.class` và tham số `-cp`. |
| `ClassNotFoundException` | Một thao tác nạp lớp theo tên tại runtime không tìm thấy lớp bằng loader được dùng. | Xác định tên lớp, loader liên quan, dependencies và nội dung JAR. |
| `NoClassDefFoundError` | JVM cần một định nghĩa lớp nhưng không thể nạp/liên kết nó, dù mã có tham chiếu hợp lệ khi biên dịch; đôi khi do lần khởi tạo trước thất bại. | Kiểm tra classpath runtime, lỗi gốc trong chuỗi `Caused by` và khởi tạo `static`. |
| `NoSuchMethodError` | Runtime có một phiên bản lớp không cung cấp phương thức mà mã đã biên dịch mong đợi. | Kiểm tra phiên bản thư viện và xung đột dependency. |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho phiên bản Java mới hơn JVM đang chạy hỗ trợ. | So sánh `java -version` và phiên bản Java dùng để biên dịch. |
| `Unable to access jarfile` | Đường dẫn JAR sai, tệp không tồn tại hoặc không đọc được. | Xác định đường dẫn tệp và quyền truy cập. |
| Spring báo không tìm thấy bean | Lớp chưa được tạo/đăng ký thành bean, vùng quét không bao phủ hoặc cấu hình điều kiện không thỏa. | Xem `@Component`, `@Bean`, package quét và cấu hình Spring. |

Hai loại lỗi dễ nhầm nhất:

- **`ClassNotFoundException`** là checked exception thường xuất hiện từ API nạp lớp động, ví dụ `Class.forName(...)`.
- **`NoClassDefFoundError`** là `LinkageError`. Ví dụ, mã đã biên dịch với `parser.jar` nhưng khi chạy bị thiếu thư viện đó: JVM chỉ phát hiện sự thiếu hụt khi cần định nghĩa lớp liên quan. Lỗi này cũng có thể xuất hiện sau khi việc khởi tạo một lớp từng thất bại; vì vậy phải đọc toàn bộ stack trace, không suy ra mọi trường hợp đều do thiếu JAR.

Một cảnh báo khác: nếu có nhiều phiên bản chứa cùng tên lớp trên classpath, ứng dụng có thể nạp phiên bản khác với phiên bản bạn dùng lúc biên dịch. Đây là nguyên nhân thường gặp của lỗi liên kết kiểu `NoSuchMethodError`. Quản lý phiên bản phụ thuộc nhất quán bằng Maven/Gradle quan trọng hơn việc tự chép hàng loạt JAR.

## 8. Cách chẩn đoán khi Java không tìm thấy lớp

Giả sử lệnh khởi chạy thất bại, hãy đi theo thứ tự từ tên lớp đến nơi chứa lớp:

1. **Xác định tên đầy đủ.** Mở tệp nguồn hoặc cấu hình điểm vào để kiểm tra package và tên lớp; ví dụ `com.example.lesson.Main`.
2. **Xác định artifact thực sự được tạo ra.** Với thư mục class, lớp phải tương ứng `com/example/lesson/Main.class` dưới một classpath root. Với JAR, xem mục trong kho lưu trữ.
3. **Xác định cách khởi chạy.** `java -cp` cần tên lớp chính; `java -jar` cần archive thực thi đúng cấu trúc/manifest.
4. **Kiểm tra phụ thuộc runtime.** Thư viện có thể tồn tại ở compile classpath nhưng vắng tại runtime. Với Spring Boot executable JAR, kiểm tra cả `BOOT-INF/lib`.
5. **Đọc nguyên nhân sâu nhất trong stack trace.** Đôi khi tên lớp báo lỗi là hậu quả của một dependency khác không tương thích hoặc một lỗi khởi tạo lớp.

Các lệnh hỗ trợ:

```bash
java -version
javac -version
jar --list --file lesson.jar
```

Trên JVM hỗ trợ thống kê nạp lớp, có thể dùng `-Xlog:class+load=info` để quan sát lớp được nạp từ nguồn nào:

```bash
java -Xlog:class+load=info -cp out com.example.lesson.Main
```

Tùy ứng dụng, đầu ra rất nhiều; nên lọc theo package đang điều tra. Với class loader tùy biến của framework, nguồn lớp được báo có thể khác cách hình dung về một classpath tuyến tính.

## 9. Ghi nhớ qua ba tình huống

**Tình huống A — Đổi vị trí tệp nguồn nhưng giữ nguyên `package`.** Tên đầy đủ của lớp vẫn do câu lệnh `package` xác định. Nếu biên dịch bằng `javac -d out`, đường dẫn bytecode đầu ra tiếp tục phản ánh package; tuy vậy công cụ build có thể không tìm tệp nguồn ở vị trí tùy ý.

**Tình huống B — Biên dịch thành công với thư viện A nhưng khi chạy không có A.** Compile classpath đã thỏa mãn trình biên dịch, còn runtime classpath thiếu định nghĩa cần thiết. Một số đường chạy có thể hoạt động trước khi chạm tới lớp bị thiếu; lỗi có thể xuất hiện muộn.

**Tình huống C — `ShopApplication.class` nằm trong `BOOT-INF/classes`.** Đây là cấu trúc bình thường của Spring Boot executable JAR. Chạy `java -jar` để launcher của Spring Boot thiết lập môi trường nạp lớp cho ứng dụng và các dependencies lồng bên trong.

Hãy luôn tách **tên lớp (package)**, **vị trí tìm lớp (classpath/class loader)** và **cách đóng gói/chạy (JAR/launcher)**. Khi ba phần này khớp nhau, cả Java thuần lẫn Spring Boot đều có cơ sở nhất quán để tìm và dùng đúng lớp.
