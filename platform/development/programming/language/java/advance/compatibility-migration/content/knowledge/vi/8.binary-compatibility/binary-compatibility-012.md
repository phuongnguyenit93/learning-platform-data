# Phân biệt lỗi nạp lớp, xác minh bytecode và liên kết

Một ứng dụng Java có thể biên dịch thành công trên JDK mới nhưng thất bại khi khởi động, nạp plugin hoặc đi vào một nhánh nghiệp vụ hiếm dùng. Stack trace có thể chứa `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, `VerifyError`, `NoSuchMethodError` hoặc `IllegalAccessError`. Các lỗi này trông giống nhau ở chỗ đều liên quan đến class và bytecode, nhưng chúng phản ánh **những vấn đề khác nhau trong quá trình JVM đưa mã đã biên dịch vào thực thi**.

Trong migration JDK, phân biệt được các giai đoạn *loading*, *verification*, *resolution* và *initialization* sẽ giúp xác định phải kiểm tra classpath, class file version, cấu trúc bytecode, chữ ký API, quyền truy cập hay logic khởi tạo. Chỉ nhìn tên exception rồi thêm JAR hoặc thay JVM option thường không giải quyết đúng nguyên nhân.

## 1. Từ file `.class` đến mã được thực thi

Mã nguồn Java được biên dịch thành bytecode trong file `.class`. File này chứa thông tin về class, các field và method, mã lệnh bytecode, constant pool và những metadata cần thiết để JVM thực hiện kiểm tra. Khi một class được sử dụng, JVM phải nạp định nghĩa class và chuẩn bị nó cho việc thực thi.

Theo mô hình của JVM, quá trình có những khái niệm chính:

```text
           Mã nguồn Java
                 |
              javac
                 v
         File .class / JAR
                 |
                 v
       1. Loading (nạp lớp)
                 |
                 v
       2. Linking (liên kết)
          +------+------+------+
          |             |      |
       Verify        Prepare  Resolve
       (xác minh)   (chuẩn bị) (phân giải)
                 |
                 v
       3. Initialization
          (khởi tạo lớp)
                 |
                 v
           Thực thi mã
```

Sơ đồ trên diễn tả các phần việc về mặt khái niệm, không phải cam kết JVM sẽ phân giải mọi tham chiếu trước khi chạy bất kỳ đoạn mã nào. JVM có thể thực hiện một số bước phân giải tham chiếu sớm hoặc trì hoãn cho đến khi chúng được sử dụng, theo các ràng buộc của đặc tả.

| Khái niệm | JVM làm gì? | Câu hỏi điều tra |
|---|---|---|
| Loading | Tìm và tạo định nghĩa runtime của class từ dữ liệu class file | Class có tồn tại và có được class loader phù hợp nhìn thấy không? |
| Verification | Kiểm tra tính hợp lệ và an toàn kiểu của bytecode | Class file có hợp lệ và bytecode có đáp ứng quy tắc của JVM không? |
| Preparation | Chuẩn bị cấu trúc runtime và giá trị mặc định cho các static field | Metadata và cấu trúc của class có phù hợp với runtime không? |
| Resolution | Chuyển tham chiếu biểu tượng tới class, field hoặc method thực tế | Đúng class/member có tồn tại, có kiểu và quyền truy cập phù hợp không? |
| Initialization | Thực hiện logic khởi tạo class như static initializer | Logic khởi tạo có ném exception hoặc phụ thuộc cấu hình/dịch vụ còn thiếu không? |

Điểm quan trọng đối với tương thích nhị phân: một file `.class` có thể được **tìm thấy và nạp**, nhưng vẫn thất bại ở bước xác minh bytecode, phân giải API hoặc khởi tạo. Vì vậy, “JAR đã có trong classpath” không đồng nghĩa với “binary tương thích”.

## 2. Loading: khi JVM tìm và định nghĩa class

Loading là quá trình JVM dùng class loader để tìm dữ liệu class file, diễn giải định dạng và tạo đối tượng `Class` tương ứng. Với ứng dụng thông thường, class có thể nằm trong thư mục output, JAR, module hoặc một nguồn do class loader tùy chỉnh cung cấp.

Các yếu tố ảnh hưởng đến loading gồm tên class, classpath/module path, class loader được dùng, cấu trúc artifact và môi trường triển khai. Những yếu tố này có thể thay đổi khi nâng JDK, đổi framework, chuyển sang container hoặc thay cơ chế plugin.

### 2.1. `ClassNotFoundException`: tìm class bằng API nhưng không thấy

`ClassNotFoundException` là checked exception thường xuất hiện khi chương trình **chủ động yêu cầu nạp class theo tên** mà class loader không tìm được định nghĩa phù hợp. Các API điển hình gồm `Class.forName(...)` và `ClassLoader.loadClass(...)`.

Ví dụ:

```java
public class PluginLoader {
    public static void main(String[] args) throws Exception {
        Class<?> plugin = Class.forName(
            "com.example.plugins.InvoicePlugin"
        );
        System.out.println(plugin.getName());
    }
}
```

Nếu class `com.example.plugins.InvoicePlugin` không được class loader tìm thấy, lệnh gọi có thể ném:

```text
java.lang.ClassNotFoundException:
    com.example.plugins.InvoicePlugin
```

Nguyên nhân thường gặp là thiếu JAR, sai tên package/class, lỗi cấu hình plugin, artifact không được đóng gói hoặc class loader đang dùng không nhìn thấy JAR.

Không nên kết luận chỉ dựa trên việc class có tồn tại ở đâu đó trên máy. Câu hỏi cần trả lời là **class loader của đường chạy đang lỗi có tìm thấy đúng class đó không?**

### 2.2. `NoClassDefFoundError`: class cần thiết không thể được cung cấp lúc chạy

`NoClassDefFoundError` là một `LinkageError` có thể xuất hiện khi một class từng được tham chiếu từ bytecode nhưng định nghĩa cần thiết không có sẵn ở runtime. Ví dụ, ứng dụng được compile với `payment-api.jar`, nhưng khi chạy lại thiếu một dependency bắc cầu mà class trong JAR cần.

```text
Compile:
  application.jar + payment-api.jar + payment-core.jar

Runtime:
  application.jar + payment-api.jar
                            |
                            v
               thiếu class từ payment-core.jar
                            |
                            v
                 NoClassDefFoundError
```

Đây là trường hợp có thể xảy ra khi build thành công nhưng artifact runtime đóng gói thiếu dependency. Lỗi cũng có thể xuất hiện sau khi class đã thất bại trong quá trình khởi tạo; khi đó cần đọc thông điệp và *cause* để tìm lỗi ban đầu.

Ví dụ:

```text
java.lang.NoClassDefFoundError: com/example/core/PaymentRule
```

Tên trong thông báo thường dùng dấu gạch chéo `/` theo tên nội bộ của class file. Hãy đối chiếu với tên class Java tương ứng `com.example.core.PaymentRule`.

### 2.3. Vì sao hai lỗi dễ bị nhầm?

| Đặc điểm | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Kiểu | Checked exception | `LinkageError` |
| Bối cảnh phổ biến | Gọi API nạp class bằng tên | JVM cần class trong quá trình liên kết/sử dụng một class đã biên dịch, hoặc class đã khởi tạo thất bại |
| Ví dụ | `Class.forName("...Plugin")` | Binary tham chiếu class thuộc JAR bị thiếu lúc chạy |
| Điều tra đầu tiên | Tên class, class loader, classpath/module path | Class thiếu, dependency runtime, cause trước đó, initialization |

Hai lỗi không phải hai tên đồng nghĩa. Trong một số hệ thống, `ClassNotFoundException` từ class loader có thể là nguyên nhân sâu dẫn tới `NoClassDefFoundError` ở nơi JVM cần class đó. Cần đọc toàn bộ chuỗi `Caused by`, không chỉ exception đầu tiên.

### 2.4. Class loader có thể làm một class “tồn tại nhưng không dùng được”

JVM xác định danh tính của một class bằng cặp **tên nhị phân và class loader định nghĩa**. Hai class có cùng tên nhưng được định nghĩa bởi hai class loader khác nhau là hai kiểu khác nhau trong runtime.

Trong ứng dụng dùng plugin, servlet container hoặc class loader tùy chỉnh, điều này có thể tạo ra các lỗi như `ClassCastException`, `LinkageError` hoặc lỗi liên quan tới loader constraint. Ví dụ, plugin mang theo bản sao của API mà host cũng có thể khiến object từ plugin không ép được sang cùng tên kiểu do host nạp.

Khi điều tra, ngoài tên class, hãy kiểm tra class loader và vị trí JAR được nạp. Không nên chữa bằng cách thêm một bản JAR thứ hai vào classpath nếu chưa biết thứ tự phân giải của loader.

## 3. Định dạng class file: `UnsupportedClassVersionError` và `ClassFormatError`

Trước khi thực thi bytecode, JVM phải hiểu được cấu trúc file `.class`. Mỗi class file có một *major version* cho biết phiên bản định dạng bytecode. Runtime cũ không thể chạy class file yêu cầu phiên bản mới hơn mức nó hỗ trợ.

### 3.1. `UnsupportedClassVersionError`

Giả sử một class được build bằng JDK 21 với target Java 21 nhưng được triển khai lên JVM 17. JVM 17 không hỗ trợ class file major version 65 của Java 21 và có thể ném:

```text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

Một số major version phổ biến:

| Phiên bản Java | Major version của class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

`UnsupportedClassVersionError` báo sự không phù hợp giữa định dạng class file và JVM đang chạy. Nó khác với `NoSuchMethodError`: ở đây JVM chưa cần đi đến việc gọi một method cụ thể của API mới.

Cách xử lý phù hợp là chạy trên runtime hỗ trợ class file đó, hoặc biên dịch lại theo mức Java được hỗ trợ. Nếu dùng compiler mới để tạo artifact cho runtime cũ, ưu tiên `javac --release N` thay vì chỉ cấu hình bytecode target, vì `--release` còn giới hạn API Java SE có thể sử dụng.

```bash
# Ví dụ: biên dịch bằng JDK mới nhưng nhắm Java 17
javac --release 17 -d out src/com/example/App.java
```

`--release` không bảo đảm các dependency bên ngoài cũng tương thích với Java 17. Một JAR phụ thuộc được build cho Java 21 vẫn có thể gây `UnsupportedClassVersionError` khi class của nó được nạp.

### 3.2. `ClassFormatError`

`ClassFormatError` cho biết dữ liệu class file không đáp ứng định dạng mà JVM yêu cầu. Ví dụ, một công cụ biến đổi bytecode tạo file `.class` hỏng, viết sai constant pool hoặc tạo cấu trúc metadata không hợp lệ.

Trong migration JDK, nguyên nhân có thể nằm ở thư viện bytecode, obfuscator, agent, code generator hoặc plugin build chưa hỗ trợ cấu trúc class file của JDK mới. Một JAR bị lỗi hoặc class file bị hỏng trong lúc đóng gói cũng có thể dẫn tới tình huống này.

Hãy kiểm tra artifact thực tế được nạp, phiên bản công cụ tạo/biến đổi class và việc có nhiều bản class cùng tên trong đường chạy hay không. Nếu chỉ có lỗi ở runtime sau khi agent can thiệp, cần so sánh class trước và sau khi biến đổi.

## 4. Verification: bytecode phải hợp lệ theo quy tắc JVM

Verification là bước JVM kiểm tra bytecode theo các quy tắc của đặc tả. Nó góp phần đảm bảo mã lệnh không sử dụng operand stack và local variables sai kiểu, không nhảy vào vị trí không hợp lệ, và tuân thủ các ràng buộc cần thiết để JVM thực thi an toàn.

Mã nguồn Java bình thường được biên dịch bởi `javac` phù hợp thường tạo bytecode hợp lệ. Lỗi verification xuất hiện nhiều hơn khi class file bị thao tác bởi công cụ bytecode, agent, obfuscator hoặc generator.

### 4.1. `VerifyError`

`VerifyError` là lỗi thuộc nhóm `LinkageError`, cho biết verifier phát hiện vấn đề ở bytecode. Một số thông báo có thể đề cập đến stack map frame, operand stack, kiểu dữ liệu hoặc nhánh điều khiển không hợp lệ.

Ví dụ thông báo minh họa:

```text
java.lang.VerifyError: Bad type on operand stack
  Exception Details:
    Location:
      com/example/Service.process()V @12: invokevirtual
```

Để điều tra, cần xác định **class file nào thực sự được verifier xử lý**. Nếu ứng dụng có agent hoặc class transformer, bytecode trên disk có thể khác bytecode thực tế được định nghĩa trong JVM. Nếu vừa nâng JDK, hãy kiểm tra tương thích của ASM, Byte Buddy, CGLIB, obfuscator hoặc công cụ sinh bytecode mà ứng dụng sử dụng.

`VerifyError` không có nghĩa là compiler thấy lỗi cú pháp trong mã nguồn Java. Cũng không nên mặc định dùng cờ tắt verification như một cách sửa lỗi; cách đúng là tìm class file hoặc công cụ đã tạo bytecode không hợp lệ.

### 4.2. Verification khác resolution

Một class có thể hợp lệ về cấu trúc và vượt qua verification nhưng vẫn không tìm thấy method mà bytecode tham chiếu. Khi đó vấn đề nằm ở resolution/linkage, không phải bytecode verifier.

Ngược lại, một class có thể chứa đủ tên class và method cần thiết nhưng thất bại verification vì cấu trúc lệnh bên trong không hợp lệ. Cả hai đều là lỗi liên quan tới binary nhưng cách sửa khác nhau.

## 5. Resolution và linking: các tham chiếu phải khớp với API runtime

Trong bytecode, lời gọi method hoặc truy cập field thường sử dụng tham chiếu biểu tượng. Tham chiếu này chỉ ra tên class, tên member và descriptor tương ứng. Khi phân giải, JVM tìm class/member thực tế và kiểm tra các điều kiện về kiểu, cách gọi và quyền truy cập.

Ví dụ descriptor của một method nhận `String` và trả về `int` có dạng:

```text
(Ljava/lang/String;)I
```

Một lời gọi được biên dịch để dùng `compute(String):int` sẽ không tự chuyển thành `compute(Object):int` hoặc `compute(String):long` nếu thư viện runtime đổi chữ ký. JVM không thực hiện lại overload resolution như compiler.

### 5.1. `NoSuchMethodError`: method cần thiết không còn đúng descriptor

Giả sử phiên bản 1 của thư viện có:

```java
package com.example.api;

public class NameFormatter {
    public String label() {
        return "ready";
    }
}
```

Ứng dụng client biên dịch với phiên bản 1:

```java
package com.example.client;

import com.example.api.NameFormatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new NameFormatter().label());
    }
}
```

Sau đó phiên bản 2 thay method bằng overload khác:

```java
package com.example.api;

public class NameFormatter {
    public String label(String prefix) {
        return prefix + "ready";
    }
}
```

Nếu giữ nguyên `Main.class` cũ và thay JAR thư viện v1 bằng v2, bytecode client vẫn yêu cầu `NameFormatter.label:()Ljava/lang/String;`. Method đó không còn trong class của v2, dẫn tới lỗi:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.NameFormatter.label()'
```

Đây là lỗi tương thích nhị phân. Khi biên dịch lại source client với thư viện v2, compiler thường báo method không còn phù hợp; nhưng lỗi runtime ở đây xảy ra vì **client đã biên dịch không được biên dịch lại**.

### 5.2. Thực nghiệm với consumer đã biên dịch

Để thấy rõ khác biệt, tạo ba file source theo đường dẫn:

```text
api-v1/com/example/api/NameFormatter.java
api-v2/com/example/api/NameFormatter.java
client/com/example/client/Main.java
```

Mỗi thư mục API chứa một phiên bản class ở ví dụ trên. Sau đó thực hiện:

```bash
# Biên dịch và đóng gói API phiên bản 1
javac -d out-v1 api-v1/com/example/api/NameFormatter.java
jar --create --file api-v1.jar -C out-v1 .

# Biên dịch client dựa trên API v1
javac -cp api-v1.jar -d out-client client/com/example/client/Main.java

# Biên dịch và đóng gói API phiên bản 2
javac -d out-v2 api-v2/com/example/api/NameFormatter.java
jar --create --file api-v2.jar -C out-v2 .

# Chạy binary client cũ với API v2
java -cp api-v2.jar:out-client com.example.client.Main
```

Trên Windows, dấu phân tách classpath là `;` thay cho `:`:

```powershell
java -cp 'api-v2.jar;out-client' com.example.client.Main
```

Điểm quan trọng là không biên dịch lại `Main.class` sau khi thay JAR. Chỉ như vậy mới xác minh được binary client đã phát hành có chạy với API mới hay không. Tương tự, không để `api-v1.jar` đồng thời nằm trong runtime classpath, vì class được nạp có thể không phải class phiên bản 2 mà bạn đang muốn kiểm tra.

### 5.3. `NoSuchFieldError`: field bị xóa, đổi tên hoặc đổi kiểu

Bytecode cũng lưu tham chiếu đến field theo tên và descriptor. Nếu field từng được khai báo:

```java
public static int RETRY_LIMIT = 3;
```

nhưng phiên bản thư viện mới xóa field hoặc đổi kiểu của nó thành `long`, binary cũ có thể báo `NoSuchFieldError`. Nếu chỉ đổi quyền truy cập mà giữ tên và descriptor, lỗi có thể là `IllegalAccessError` thay vì `NoSuchFieldError`.

Một lưu ý với hằng `static final` có giá trị hằng theo quy tắc compile-time constant: compiler có thể đưa giá trị trực tiếp vào bytecode consumer (*inlining*). Vì vậy, thay đổi giá trị hằng trong thư viện chưa chắc làm client cũ thấy giá trị mới. Đây là một dạng rủi ro tương thích hành vi dù binary có thể không báo lỗi liên kết.

### 5.4. `IllegalAccessError`: member có tồn tại nhưng không còn quyền truy cập

Giả sử thư viện đổi method `public` thành `protected`, package-private hoặc `private` nhưng vẫn giữ tên và descriptor. Client đã biên dịch trước đây có thể tìm thấy method nhưng không còn quyền gọi nó. JVM có thể ném `IllegalAccessError` khi kiểm tra quyền truy cập.

Tương tự, trong ứng dụng dùng module path, một package không còn được `exports` cho module consumer có thể làm truy cập tới kiểu public bị từ chối. Cần xem đồng thời access modifier, package, class loader, quan hệ subclass và cấu hình module.

Việc thêm `--add-opens` chỉ liên quan đến quyền truy cập sâu bằng reflection; nó không phải cách chung để sửa mọi lỗi liên kết thông thường. Với quyền truy cập kiểu public giữa module, điều kiện `exports` và readability mới là yếu tố cần kiểm tra.

### 5.5. `IncompatibleClassChangeError` và `AbstractMethodError`

`IncompatibleClassChangeError` là nhóm lỗi xảy ra khi một định nghĩa class/member ở runtime không phù hợp với giả định đã có trong binary lúc compile. Những dạng như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` và `AbstractMethodError` đều thuộc nhóm này.

Ví dụ, binary được biên dịch để gọi một method instance nhưng runtime lại cung cấp cấu trúc method static không phù hợp, hoặc interface/class thay đổi theo cách khiến cách gọi không còn hợp lệ, có thể gây lỗi trong nhóm này.

`AbstractMethodError` có thể xuất hiện khi lời gọi cần một implementation cụ thể nhưng runtime không tìm được implementation phù hợp, ví dụ trong các tổ hợp class/interface được biên dịch với những phiên bản khác nhau.

Không nên chữa `AbstractMethodError` bằng cách đoán một method bị thiếu trong source hiện tại; hãy so sánh binary và hệ phân cấp class/interface của các artifact thực sự được nạp.

## 6. Initialization: class có thể nạp và liên kết được nhưng khởi tạo thất bại

Khởi tạo class diễn ra khi JVM thực thi các bước khởi tạo cần thiết, bao gồm logic của static initializer và việc gán static field theo mã khởi tạo. Đây là giai đoạn khác với loading và verification.

Ví dụ:

```java
public class FeatureFlags {
    static final String REGION;

    static {
        REGION = System.getenv("APP_REGION");
        if (REGION == null) {
            throw new IllegalStateException("APP_REGION is missing");
        }
    }
}
```

Lần sử dụng đầu tiên buộc class khởi tạo có thể dẫn đến `ExceptionInInitializerError`, với *cause* là `IllegalStateException`. Những lần sử dụng sau trong cùng runtime có thể gặp `NoClassDefFoundError` với thông điệp liên quan đến class không thể được khởi tạo.

Khi thấy:

```text
java.lang.NoClassDefFoundError: Could not initialize class ...
```

đừng vội kết luận thiếu JAR. Hãy tìm exception đầu tiên trước đó trong log và nguyên nhân của initialization failure: biến môi trường, file cấu hình, kết nối database, lỗi parse dữ liệu, phiên bản thư viện hoặc static dependency.

### 6.1. `Class.forName` có thể vừa nạp vừa khởi tạo

Lệnh `Class.forName("com.example.FeatureFlags")` thông thường yêu cầu khởi tạo class sau khi tìm thấy và liên kết phù hợp, nên có thể làm lộ lỗi static initializer. Nếu muốn kiểm tra việc tìm/nạp class mà chưa khởi tạo, có overload:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName(
    "com.example.FeatureFlags", false, loader
);
```

Tham số `false` yêu cầu không khởi tạo class như một phần của lời gọi này. Dù vậy, class hoặc các dependency liên quan vẫn có thể cần được nạp, kiểm tra hay liên kết theo yêu cầu của JVM. Không nên coi thao tác này là phép thử chứng minh class chắc chắn sẽ khởi tạo hoặc hoạt động thành công.

## 7. Sơ đồ chẩn đoán theo triệu chứng

Khi một ứng dụng lỗi sau khi nâng JDK hoặc dependency, có thể bắt đầu từ exception chính rồi tìm giai đoạn phù hợp:

```text
Ứng dụng lỗi khi sử dụng một class
                   |
                   v
          Xem exception và cause
                   |
      +------------+-------------+
      |            |             |
 ClassNotFound  Unsupported      VerifyError /
 Exception     ClassVersion     ClassFormatError
      |            |             |
      v            v             v
 Kiểm tra      Kiểm tra      Kiểm tra bytecode,
 loader,       major version  generator, agent,
 classpath     và JVM đích    công cụ biến đổi
                   |
                   v
          Nếu class nạp được
                   |
          +--------+--------+
          |                 |
  NoSuchMethod/Field   IllegalAccess /
  /AbstractMethod      IncompatibleClassChange
          |                 |
          v                 v
  So descriptor,      So modifier, class/
  dependency/JAR      interface, module
          |
          v
  Nếu lỗi khởi tạo: xem ExceptionInInitializerError
  hoặc NoClassDefFoundError (Could not initialize class)
```

Sơ đồ giúp định hướng điều tra, nhưng không thay thế việc đọc stack trace đầy đủ. Một lỗi cấp cao có thể bọc lỗi gốc; ví dụ framework có thể ném exception tạo bean, còn cause bên trong là `NoSuchMethodError` hoặc `ExceptionInInitializerError`.

| Lỗi nổi bật | Giai đoạn/khía cạnh thường liên quan | Bằng chứng cần kiểm tra đầu tiên |
|---|---|---|
| `ClassNotFoundException` | Nạp class theo tên | Tên class, class loader, JAR và cấu hình runtime |
| `NoClassDefFoundError` | Không cung cấp được định nghĩa class cần thiết hoặc class khởi tạo thất bại | Dependency thiếu, thông điệp lỗi và cause trước đó |
| `UnsupportedClassVersionError` | Định dạng class file/JVM | Major version và phiên bản runtime thực sự |
| `ClassFormatError` | Cấu trúc class file | Artifact, bytecode generator/transformer, file `.class` |
| `VerifyError` | Bytecode verification | Bytecode tại vị trí lỗi, stack map frame, transformer/agent |
| `NoSuchMethodError` | Phân giải method | Method descriptor trong consumer và API của JAR runtime |
| `NoSuchFieldError` | Phân giải field | Field name/descriptor trong consumer và API runtime |
| `IllegalAccessError` | Kiểm tra quyền truy cập khi liên kết | Modifiers, package, module exports và class loader |
| `AbstractMethodError` | Liên kết/cách dispatch method | Class/interface hierarchy và các binary khác phiên bản |
| `ExceptionInInitializerError` | Khởi tạo class | Static initializer và exception gốc |

## 8. Dùng công cụ JDK để xác minh bytecode và liên kết

Khi điều tra, ưu tiên bằng chứng từ **artifact thực tế được triển khai**. Mã nguồn trên nhánh hiện tại có thể không giống class file đang chạy trong production.

### 8.1. Xem class nào có trong JAR bằng `jar`

```bash
jar --list --file application.jar
```

Có thể tìm trực tiếp class cần kiểm tra trong danh sách, ví dụ `com/example/api/NameFormatter.class`. Nếu dùng executable/fat JAR, class và dependency có thể nằm trong cấu trúc riêng như thư mục chứa nested JAR. Khi đó cần hiểu cách launcher của framework tạo classpath/runtime class loader.

Nếu một class xuất hiện trong nhiều JAR, cần xác định bản nào thực sự được JVM nạp. Chỉ có tên file trong archive không đủ để kết luận runtime đang dùng class đó.

### 8.2. Xem class file version bằng `javap -verbose`

```bash
javap -verbose -classpath application.jar com.example.App
```

Trong output, tìm các dòng tương tự:

```text
minor version: 0
major version: 61
```

Major version 61 tương ứng Java 17. Cần dùng đúng file `.class` hoặc đúng JAR mà runtime đã nạp. Nếu ứng dụng có nhiều version class trong cùng một JAR, phải xem class thực tế phù hợp với runtime mục tiêu.

### 8.3. Xem method descriptor bằng `javap -s -p`

```bash
javap -classpath api-v1.jar -s -p com.example.api.NameFormatter
javap -classpath api-v2.jar -s -p com.example.api.NameFormatter
```

`-s` in descriptor của các member; `-p` hiển thị cả member không public. So sánh hai phiên bản giúp phát hiện method bị đổi tham số, kiểu trả về, tên hoặc quyền truy cập.

Ví dụ:

```text
public java.lang.String label();
  descriptor: ()Ljava/lang/String;
```

Nếu bản mới chỉ có `label(String)`, descriptor đã khác. Điều này giải thích vì sao bytecode client cũ không thể tự chuyển sang lời gọi mới.

### 8.4. Xem bytecode và constant pool của consumer

```bash
javap -c -verbose -classpath out-client com.example.client.Main
```

`-c` cho biết các bytecode instruction, còn `-verbose` hiển thị thông tin như constant pool, method references và major version. Với `NoSuchMethodError`, hãy tìm lời gọi `invokevirtual`, `invokestatic` hoặc các instruction gọi method tương ứng, sau đó đọc tham chiếu `Methodref`/`InterfaceMethodref`.

Ví dụ một dòng tham chiếu có thể thể hiện:

```text
Methodref com/example/api/NameFormatter.label:()Ljava/lang/String;
```

Đối chiếu tham chiếu này với class trong JAR thực tế lúc chạy. Đây là cách xác minh chính xác binary đang yêu cầu phương thức nào, thay vì suy luận từ source hiện tại.

### 8.5. Kiểm tra dependency bằng `jdeps`

`jdeps` phân tích dependency tĩnh của class/JAR. Ví dụ:

```bash
jdeps --recursive application.jar
```

Nếu cần cung cấp đường dẫn dependency ngoài JAR:

```bash
jdeps --class-path 'libs/*' --recursive application.jar
```

`jdeps` hữu ích để nhận diện những package hoặc module mà artifact tham chiếu tĩnh. Công cụ không thể phát hiện đầy đủ các class chỉ được nạp qua reflection, tên chuỗi, service loader hoặc cơ chế plugin động. Vì vậy, nó là đầu vào cho điều tra, không phải chứng nhận mọi class runtime đều có mặt.

Với multi-release JAR, cần lưu ý các class theo phiên bản Java trong `META-INF/versions/` và chọn cấu hình phân tích phù hợp, chẳng hạn tùy chọn `--multi-release` của `jdeps`.

### 8.6. Theo dõi class được nạp khi chạy

Trên các JDK hiện đại, unified logging có thể ghi hoạt động nạp class:

```bash
java -Xlog:class+load=info -cp 'libs/*:app.jar' com.example.Main
```

Trên Windows, cần điều chỉnh dấu phân tách classpath thành `;`. Log class loading giúp xác định class được tải từ JAR hoặc module nào. Tùy phiên bản JDK và mức log, thông tin được in có thể khác nhau.

Hãy lọc log theo class đang lỗi và đối chiếu đúng tiến trình thực thi. Trong một hệ thống có nhiều JAR chứa class cùng tên, đây thường là bằng chứng trực tiếp cho thấy bản nào đã được chọn tại runtime.

## 9. Những nguyên nhân đặc thù trong migration JDK

### 9.1. Build bằng JDK mới nhưng runtime vẫn cũ

JDK mới có thể tạo class file mà runtime cũ không hiểu. Nếu chỉ thay compiler mà chưa thay runtime, ứng dụng có thể gặp `UnsupportedClassVersionError`. Dùng `--release` để nhắm mức Java được hỗ trợ và chạy test trên runtime thấp nhất còn được hỗ trợ.

### 9.2. API hoặc module chuẩn bị loại bỏ

Một số API/module từng được JDK cung cấp sẵn đã bị loại bỏ ở những bản phát hành sau. Ví dụ, các module Java EE và CORBA bị loại khỏi JDK từ Java 11. Ứng dụng dựa vào JAXB được cung cấp sẵn trước đây có thể gặp lỗi compile hoặc runtime nếu không bổ sung dependency phù hợp.

Khi điều tra, cần xác định class đó từng thuộc JDK hay thuộc dependency ngoài, và bản JDK mới có còn cung cấp nó không. Đừng cố giải quyết bằng cách đổi class loader khi vấn đề là thư viện đã không còn nằm trong runtime.

### 9.3. Framework và bytecode library chưa hỗ trợ JDK mới

Framework, agent hoặc thư viện tạo proxy có thể sinh/biến đổi class file. Khi chúng chưa hiểu class file version mới hoặc quy tắc verifier của runtime, ứng dụng có thể gặp `ClassFormatError`, `VerifyError` hoặc lỗi nạp class khác.

Hãy đối chiếu phiên bản Spring, Hibernate, Byte Buddy, ASM, Mockito, công cụ coverage và agent giám sát với JDK mục tiêu. Nếu lỗi chỉ xuất hiện khi test runner hoặc agent đang hoạt động, kiểm tra công cụ đó trước khi sửa mã nghiệp vụ.

### 9.4. Thay dependency nhưng binary client chưa được biên dịch lại

Một ứng dụng đã biên dịch với version A của thư viện có thể chạy với version B ở runtime do conflict transitive dependency, classpath order hoặc artifact đóng gói khác với lúc build. Đây là nguyên nhân phổ biến của `NoSuchMethodError` và `NoSuchFieldError`.

Hãy đối chiếu dependency tree lúc build với danh sách JAR thực tế lúc chạy. Kiểm tra sự khác nhau giữa `compileOnly`, `provided`, `runtimeOnly` và dependency đóng gói khi dùng Maven/Gradle. Không nên chỉ dựa vào dependency declaration mà bỏ qua cách artifact được tạo và triển khai.

### 9.5. Module path và reflection thay đổi quyền truy cập

Khi chuyển từ classpath sang module path, module readability, `exports` và `opens` có thể làm thay đổi khả năng truy cập tới API. Một lỗi gọi trực tiếp có thể là `IllegalAccessError`, trong khi deep reflection có thể ném `InaccessibleObjectException`.

Phân biệt rõ: truy cập bytecode thông thường cần các điều kiện visibility/module export; deep reflection cần điều kiện mở package. Tùy chọn `--add-exports` và `--add-opens` không cùng mục đích và không thay thế việc nâng cấp thư viện truy cập nội bộ JDK.

### 9.6. Multi-release JAR và class được chọn theo phiên bản

Một multi-release JAR có thể chứa class cơ sở và các class riêng cho Java 9 trở lên trong `META-INF/versions/N/`. Runtime có thể chọn class phù hợp với phiên bản của nó. Vì vậy, cùng một JAR có thể cung cấp định nghĩa class khác nhau trên Java 11 và Java 21.

Khi lỗi chỉ xuất hiện ở một runtime, cần kiểm tra manifest và các entry versioned trong JAR, đồng thời xác minh class thực tế được nạp. Không nên chỉ xem class cơ sở rồi kết luận API runtime giống nhau trên mọi JDK.

## 10. Quy trình điều tra có thể áp dụng trong dự án

Để tránh sửa sai chỗ, có thể điều tra theo thứ tự sau.

### Bước 1: Ghi lại môi trường thực tế

Thu thập phiên bản JDK và vendor, command line, classpath/module path, thông tin container, dependency và JAR đang triển khai. Nếu có nhiều instance, xác định chính xác instance phát sinh lỗi.

```bash
java -version
```

Lệnh này nên được chạy trong cùng image/container hoặc host mà ứng dụng đang sử dụng, thay vì chỉ chạy trên máy lập trình viên.

### Bước 2: Tìm lỗi gốc trong stack trace

Đọc exception đầu tiên có ý nghĩa và chuỗi `Caused by`. Đặc biệt với `NoClassDefFoundError: Could not initialize class`, cần tìm lỗi khởi tạo ban đầu. Nếu framework báo lỗi tạo bean, hãy tìm cause là class loading/linkage error.

### Bước 3: Xác minh artifact chứa class và phiên bản bytecode

Kiểm tra JAR bằng `jar --list`; kiểm tra major version, method/field và descriptor bằng `javap`. Nếu có nhiều bản class, xác định bản nào được runtime nạp từ log class loading.

### Bước 4: Đối chiếu binary consumer với API runtime

Với `NoSuchMethodError`/`NoSuchFieldError`, dùng `javap -c -verbose` để xem tham chiếu mà consumer đang yêu cầu và `javap -s -p` để xem member trong thư viện runtime. Với `IllegalAccessError`, đối chiếu access flags, package và module exports.

### Bước 5: Kiểm tra class loader và dependency tree

Xem class loader nào nạp class, liệu có bản duplicate và thứ tự JAR ra sao. Kiểm tra artifact ngoài build, container layer, plugin folder, fat JAR hoặc dependency bị loại khỏi runtime.

### Bước 6: Tái hiện bằng binary cũ

Giữ artifact consumer được biên dịch với phiên bản dependency cũ; thay đúng một dependency bằng bản mới rồi chạy cùng các luồng liên quan. Điều này cho thấy liệu có phá vỡ tương thích nhị phân hay không. Nếu biên dịch lại consumer ngay, có thể che mất lỗi runtime mà binary đã triển khai sẽ gặp.

### Bước 7: Sửa nguyên nhân và chạy kiểm thử phù hợp

Tùy lỗi, có thể cần thay runtime, dùng `--release`, thêm dependency thiếu, loại bỏ phiên bản JAR trùng, nâng framework/agent, giữ lại API có descriptor cũ, sửa module export hoặc điều chỉnh logic khởi tạo. Sau đó chạy test tương thích trên JDK mục tiêu và các phiên bản runtime còn được hỗ trợ.

| Nguyên nhân đã xác nhận | Hướng xử lý |
|---|---|
| Class không nằm trong runtime artifact | Đóng gói/cung cấp dependency đúng và kiểm tra class loader |
| Class file quá mới cho JVM | Chọn runtime phù hợp hoặc biên dịch lại với `--release` được hỗ trợ |
| Bytecode không hợp lệ | Sửa/nâng công cụ tạo hoặc biến đổi bytecode, phát hành lại artifact |
| Method/field đổi descriptor | Giữ API tương thích hoặc build lại tất cả consumer theo hợp đồng mới |
| Quyền truy cập bị thu hẹp | Khôi phục bề mặt API tương thích hoặc di chuyển consumer sang API công khai được hỗ trợ |
| Runtime dùng sai phiên bản dependency | Sửa dependency resolution/packaging và xác nhận JAR được nạp |
| Static initializer thất bại | Sửa lỗi khởi tạo gốc, cấu hình và dependency cần thiết |

## 11. Các hiểu nhầm thường làm kéo dài sự cố

**“Có class trong JAR thì chắc chắn sẽ chạy.”** JVM còn phải hiểu định dạng, xác minh bytecode, phân giải các tham chiếu và khởi tạo class khi cần. Class có mặt chưa đủ bảo đảm khả năng thực thi.

**“`ClassNotFoundException` và `NoClassDefFoundError` cùng là thiếu JAR.”** Chúng có ngữ cảnh khác nhau; `NoClassDefFoundError` còn có thể xuất hiện sau khi initialization thất bại. Phải đọc nguyên nhân gốc.

**“`NoSuchMethodError` nghĩa là thiếu source method.”** Bytecode cần một method có đúng tên và descriptor ở runtime. Source hiện tại có một overload tên giống chưa chắc đáp ứng tham chiếu cũ.

**“Ứng dụng compile thành công thì đã tương thích nhị phân.”** Compile thường tạo binary mới. Nó không xác minh JAR/client đã phát hành trước đó còn liên kết với API mới.

**“JVM sẽ phân giải mọi method ngay lúc khởi động.”** JVM có quyền thực hiện resolution theo thời điểm phù hợp của đặc tả; lỗi có thể chỉ xuất hiện khi một đường chạy ít dùng được kích hoạt.

**“Đổi `JAVA_HOME` là sửa được mọi lỗi class.”** `JAVA_HOME` chỉ ảnh hưởng việc chọn môi trường theo cách công cụ sử dụng. Nó không tự giải quyết dependency thiếu, descriptor đổi, class loader conflict hoặc bytecode bị sinh sai.

**“Chỉ cần thay framework, không cần xem agent hoặc plugin.”** Công cụ biến đổi bytecode, test runner, coverage và APM agent cũng có thể nạp hoặc tạo class. Cần xem toàn bộ chuỗi runtime khi lỗi chỉ xuất hiện ở một môi trường.

## 12. Bảng kiểm trước khi kết luận tương thích nhị phân

- [ ] Đã ghi nhận JDK thực tế, vendor, số build, classpath/module path và runtime artifact.
- [ ] Đã đọc toàn bộ stack trace và chuỗi `Caused by`.
- [ ] Đã phân biệt lỗi nạp class, định dạng class file, verification, resolution và initialization.
- [ ] Đã xác định class loader và JAR thực sự cung cấp class lỗi.
- [ ] Đã kiểm tra major version với phiên bản JVM đích.
- [ ] Đã so sánh method/field descriptor của binary consumer và thư viện runtime.
- [ ] Đã kiểm tra access modifier, module exports/opens nếu có lỗi truy cập.
- [ ] Đã kiểm tra dependency bắc cầu, JAR trùng và cách đóng gói runtime.
- [ ] Đã xem xét multi-release JAR, bytecode generator và agent khi phù hợp.
- [ ] Đã chạy artifact consumer cũ với dependency mới mà không biên dịch lại.
- [ ] Đã kiểm thử các luồng nạp class động, plugin, reflection và khởi tạo ít dùng.
- [ ] Đã ghi lại kết quả và phương án sửa gắn với đúng nguyên nhân.

## 13. Kết luận

Lỗi liên quan đến class trong Java xuất hiện ở nhiều giai đoạn khác nhau. `ClassNotFoundException` thường liên quan đến lời gọi nạp class theo tên; `NoClassDefFoundError` liên quan đến việc không cung cấp được định nghĩa class cần thiết hoặc class đã khởi tạo thất bại; `UnsupportedClassVersionError` và `ClassFormatError` chỉ ra vấn đề định dạng; `VerifyError` liên quan đến quy tắc bytecode; các lỗi như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` và `AbstractMethodError` thường chỉ ra việc liên kết với API runtime không còn khớp với giả định lúc compile.

Trong migration JDK, cần xác minh **đúng artifact, đúng class loader, đúng bytecode và đúng phiên bản dependency**. Công cụ `jar`, `javap`, `jdeps` và log class loading giúp biến giả định thành bằng chứng. Kiểm thử cả source mới lẫn binary consumer đã biên dịch trước đó sẽ giúp phát hiện những lỗi mà build thành công hoặc một lần khởi động đơn giản có thể bỏ sót.
