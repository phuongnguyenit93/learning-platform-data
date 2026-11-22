# Resolution: phân giải tham chiếu ký hiệu trong vòng đời lớp Java

**Resolution (phân giải tham chiếu ký hiệu)** là công đoạn của **linking** trong vòng đời lớp trên JVM. Khi biên dịch mã nguồn Java, compiler thường chưa thể gắn các chỗ sử dụng lớp, trường, phương thức với đối tượng runtime cụ thể. Thay vào đó, class file lưu các **symbolic reference**: thông tin mô tả tên và kiểu của đích cần truy cập. Khi resolution diễn ra, JVM chuyển một tham chiếu như vậy thành thực thể runtime tương ứng, đồng thời thực hiện những kiểm tra liên quan như tìm thành viên, quyền truy cập và ràng buộc class loader.

Đây là một nguyên nhân quan trọng khiến **biên dịch thành công nhưng ứng dụng vẫn lỗi ở thời gian chạy**: tên phương thức còn trong bytecode của ứng dụng nhưng JAR được tải lúc chạy đã thay đổi API; lớp tồn tại nhưng không được phép truy cập; hoặc cùng tên class được định nghĩa bởi class loader không tương thích.

## 1. Đặt resolution vào đúng vị trí

```text
.java
  │ javac: phân tích nguồn, kiểm tra kiểu, sinh class file
  ▼
.class: bytecode + constant pool chứa symbolic references
  │
  ▼
Loading: loader tìm/định nghĩa lớp trong JVM
  │
  ▼
Linking
  ├─ Verification: bytecode/class file hợp lệ?
  ├─ Preparation: tạo và đặt giá trị mặc định cho static fields
  └─ Resolution: symbolic reference → đích runtime + kiểm tra liên kết
          │
          ├─ Có thể được thực hiện sớm trong linking
          └─ Có thể được trì hoãn đến lúc tham chiếu được sử dụng
  │
  ▼
Initialization khi Java yêu cầu active use
  │
  ▼
Thực thi các phương thức, tạo object theo nhu cầu
```

Sơ đồ thể hiện **quan hệ logic**, không ép resolution phải kết thúc toàn bộ trước khi initialization. Theo JVM Specification, verification và preparation phải hoàn thành trước initialization, nhưng JVM có thể phân giải các symbolic reference theo cách **eager** (sớm) hoặc **lazy** (theo nhu cầu). Một số resolution có thể tiếp tục sau khi lớp đã initialized. Nếu resolution phát hiện lỗi, JVM phải báo lỗi ở thời điểm chương trình trực tiếp hoặc gián tiếp sử dụng tham chiếu gây lỗi.

| Bước | Câu hỏi chính | Phân biệt với resolution |
| --- | --- | --- |
| Loading | Dữ liệu lớp nào được đưa vào JVM, class loader nào định nghĩa? | Có lớp runtime chưa có nghĩa mọi member reference đã phân giải. |
| Verification | Định dạng, cấu trúc và bytecode có hợp lệ không? | Kiểm tra bytecode khác với xác định đích cho từng symbolic reference. |
| Preparation | Static fields có giá trị mặc định nào? | Chưa thực thi phần lớn static initializer Java. |
| **Resolution** | Tên/descriptor này trỏ tới class, field, method hay call site runtime nào? | Có thể kéo theo loading và access checks; không đồng nghĩa gọi phương thức. |
| Initialization | Khối `static` và static initializer có được thực thi chưa? | Thường do `new`, `getstatic`, `putstatic`, `invokestatic` hoặc các active use khác kích hoạt. |
| Method selection | Với đối tượng nhận thực tế, implementation nào được chọn? | Thường xảy ra khi chạy `invokevirtual`/`invokeinterface` sau khi method reference đã được resolved. |

Không coi thứ tự trên là dấu vết thực thi chính xác của mọi JVM. Resolution là khái niệm được đặc tả ở cấp JVM; cách JVM cache thông tin hay tối ưu hóa trong bộ nhớ thuộc chi tiết triển khai.

## 2. Symbolic reference đến từ đâu?

Một tệp `.class` có **constant pool**, bao gồm string literal, giá trị hằng, tên/descriptor và các entry mô tả tham chiếu. JVM xây dựng **run-time constant pool** tương ứng cho lớp đã được tạo. Nhiều bytecode instructions trỏ vào đó thông qua **chỉ số**, thay vì mang địa chỉ máy của lớp hoặc phương thức.

Ví dụ Java:

```java
int n = Calculator.total;
String text = Calculator.format(n);
```

Compiler có thể tạo những tham chiếu tượng trưng tương tự:

```text
CONSTANT_Fieldref       demo/Calculator.total:I
CONSTANT_Methodref      demo/Calculator.format:(I)Ljava/lang/String;
```

Ở đây:

- `demo/Calculator` là tên internal của class trong class file; binary name Java tương ứng là `demo.Calculator`.
- `total` là tên field; descriptor `I` nghĩa là `int`.
- `format` là tên method; descriptor `(I)Ljava/lang/String;` nghĩa là nhận một `int` và trả về `java.lang.String`.
- Tên field/method và **descriptor** tạo nên định danh thành viên mà bytecode yêu cầu. JVM descriptor của method bao gồm cả return type; chỉ nhìn tên `format` là chưa đủ để hiểu một tham chiếu trong constant pool.

Đây là cú pháp mô tả giản lược để học, không phải đường dẫn bắt buộc của JAR. Các entry thật có chỉ số `#...`, liên kết `Class`/`NameAndType` và bytecode offset; dùng `javap -verbose` để xem cấu trúc chính xác.

Các dạng tham chiếu phổ biến:

| Constant-pool entry | Đại diện cho | Một bytecode liên quan |
| --- | --- | --- |
| `CONSTANT_Class` | Lớp/interface/array type | `new`, `checkcast`, `instanceof`, `anewarray`, `ldc` với class literal |
| `CONSTANT_Fieldref` | Field theo chủ thể, tên, field descriptor | `getfield`, `putfield`, `getstatic`, `putstatic` |
| `CONSTANT_Methodref` | Method của class theo tên, method descriptor | `invokevirtual`, `invokespecial`, `invokestatic` |
| `CONSTANT_InterfaceMethodref` | Method được tham chiếu qua interface | `invokeinterface`; một số lệnh gọi static/private interface methods tùy opcode |
| `CONSTANT_MethodType` | Kiểu lời gọi gồm tham số và kiểu trả về | `ldc` cho method-type constant |
| `CONSTANT_MethodHandle` | Hành vi truy cập field/gọi method theo reference kind | `ldc` và thành phần bootstrap |
| `CONSTANT_Dynamic` | Giá trị hằng được tính qua bootstrap method | `ldc`/`ldc_w`/`ldc2_w` theo loại |
| `CONSTANT_InvokeDynamic` | Mô tả call site được liên kết động | `invokedynamic` |

Các entry tên/descriptor như `CONSTANT_Utf8` và `CONSTANT_NameAndType` là thành phần cấu trúc của tham chiếu. Đừng hiểu mọi string hoặc số trong constant pool đều trải qua field/method resolution.

## 3. Cơ chế resolution: từ cái tên đến đích runtime

Xét một instruction như `getstatic demo/Calculator.total:I` nằm trong bytecode của `demo.Main`:

1. **Nhận symbolic reference.** Bytecode trỏ tới entry `Fieldref` trong run-time constant pool của lớp đang chứa instruction.
2. **Phân giải chủ thể class/interface.** JVM dùng defining loader của lớp đang chứa tham chiếu để tạo/tra cứu lớp chủ thể theo quy tắc loading và delegation; từ đó xác định runtime type đúng, thay vì tìm class chỉ bằng chuỗi tên.
3. **Tra cứu field/method phù hợp.** Với field, JVM dùng tên và descriptor, duyệt theo quy tắc lookup của JVM. Với method hoặc interface method, quy tắc tra cứu khác nhau và có thể xét superclass/superinterface.
4. **Kiểm tra access và loading constraints.** Thành viên có thực sự truy cập được từ lớp tham chiếu hay không? Các kiểu xuất hiện trong descriptor có thống nhất qua các defining loaders liên quan hay không?
5. **Hoàn thành hoặc thất bại.** Nếu thành công, JVM có kết quả runtime tương ứng cho reference; nếu thất bại, lỗi liên kết phù hợp được báo. Các điều kiện riêng của instruction như static/instance cũng có thể gây lỗi liên kết.
6. **Tiếp tục ngữ nghĩa instruction.** Ví dụ `getstatic` có thể làm class khai báo field được initialized trước khi đọc giá trị; `invokevirtual` sẽ còn chọn implementation dựa trên lớp runtime của receiver.

Tham chiếu `demo.Calculator` được resolve ở ngữ cảnh **lớp chứa constant-pool entry**, chứ không phải chọn ngẫu nhiên class có tên đó trong toàn bộ tiến trình. Điều này quyết định tính đúng đắn của kiến trúc plugin sử dụng nhiều class loader.

### Vì sao không phải "thay chuỗi tên bằng địa chỉ máy"?

Kết quả resolution về mặt đặc tả có thể là class/interface, field, method, `MethodType`, `MethodHandle` hoặc một hằng/call site runtime. JVM triển khai có thể lưu dữ liệu tra cứu trong cache hoặc cấu trúc tối ưu, nhưng **không có giao diện Java chuẩn trả về con trỏ native** cho một entry constant pool. Hãy dùng từ "**ràng buộc symbolic reference với thực thể runtime**" thay cho suy diễn mọi trường hợp đều trở thành một địa chỉ hàm.

## 4. Các trường hợp resolution cụ thể

### 4.1. Class và interface resolution

Với tham chiếu từ lớp `D` đến kiểu có tên `N`:

- JVM dùng **defining loader của `D`** để yêu cầu tạo/tra cứu kiểu có tên `N`. Loader có thể ủy quyền cho parent. Class được tạo thực tế có thể có **defining loader khác** với loader nhận yêu cầu ban đầu.
- Nếu tham chiếu là array class có phần tử kiểu tham chiếu, resolution liên quan đến kiểu phần tử cũng được xử lý theo quy tắc tương ứng.
- JVM kiểm tra quyền truy cập của `D` đến kiểu đích.

Nếu loại đó không thể được tìm/tạo, resolution có thể thất bại do lỗi loading. Nếu class tồn tại nhưng `D` không được phép truy cập, resolution có thể báo `IllegalAccessError`. Sự tồn tại của một `.class` trong JAR không tự bảo đảm JVM có thể resolve đến nó.

Ví dụ named module còn cần xét **module readability/exports**; public type trong package không export cho module yêu cầu vẫn có thể không truy cập hợp lệ từ module đó. Quy tắc access ở runtime xét package, module và định danh class loader theo Java Platform Module System, không chỉ từ khóa `public`.

### 4.2. Field resolution

Một `Fieldref` xác định **class/interface đích, field name, field descriptor**. Sau khi resolve class, JVM tra cứu field được khai báo ở class đó, tiếp tục theo các quy tắc lookup qua superinterfaces và superclass. Nếu không tìm thấy tên **và descriptor** phù hợp, JVM ném `NoSuchFieldError`; nếu thấy nhưng caller không có quyền truy cập, có thể là `IllegalAccessError`.

Cần tách **resolution của field** khỏi kiểm tra instruction: `getfield` yêu cầu instance field, còn `getstatic` yêu cầu static field. Nếu binary API đổi static thành instance mà bytecode caller vẫn sử dụng opcode cũ, lỗi có thể là `IncompatibleClassChangeError`, cho dù tên và descriptor field vẫn khớp.

Ví dụ các descriptor:

```text
int count                → count:I
long total               → total:J
String label             → label:Ljava/lang/String;
int[] numbers            → numbers:[I
String[] names           → names:[Ljava/lang/String;
```

### 4.3. Class method resolution

Với `Methodref`, JVM trước tiên resolve class chủ thể rồi tra cứu method phù hợp, bao gồm các quy tắc đặc biệt cho superclass và default interface methods. Nếu không tìm được method theo tên và descriptor, kết quả thường là `NoSuchMethodError`. Nếu entry `Methodref` lại trỏ đến interface ở nơi quy tắc yêu cầu class, JVM có thể báo `IncompatibleClassChangeError`.

Constructor có tên JVM đặc biệt `<init>`; class initializer là `<clinit>`. Không xem `<clinit>` là phương thức bình thường có thể gọi trực tiếp bằng source Java.

Một thay đổi source-level nhìn có vẻ nhỏ vẫn có thể phá compatibility ở bytecode:

```text
Trước: String version() → descriptor ()Ljava/lang/String;
Sau:   int version()    → descriptor ()I
```

Bên gọi cũ đã biên dịch vẫn đòi `()Ljava/lang/String;`. Nếu runtime chỉ có `()I`, Java không tự "chuyển đổi return type" để cứu link. Ví dụ chạy được ở phần thực hành B sẽ quan sát lỗi này.

### 4.4. Interface method resolution

Với `InterfaceMethodref`, JVM phải resolve một **interface**, tra cứu method có tên/descriptor yêu cầu, và tuân thủ quy tắc với method kế thừa (kể cả các tình huống default methods). Không thể thay thế máy móc bằng thuật toán lookup class. Nếu runtime class thực thi interface khác kỳ vọng của caller, việc resolve và/hoặc method selection có thể gặp lỗi.

Hai giai đoạn khác nhau:

- **Interface method resolution:** xác định tham chiếu từ bytecode `invokeinterface` là method nào ở cấp khai báo/hệ kiểu.
- **Method selection:** khi instruction thực sự gọi, xét **receiver runtime class** để chọn implementation thích hợp (ví dụ `EnglishGreeting` hay `VietnameseGreeting`).

Bởi vậy "resolve method" không nhất thiết có nghĩa cố định một implementation cho mọi instance nhận lời gọi.

### 4.5. Method type, method handle, dynamic constant và `invokedynamic`

Java hiện đại còn có các kiểu resolution:

- **Method type:** phân giải những class/interface xuất hiện trong descriptor; kết quả là một `java.lang.invoke.MethodType`.
- **Method handle:** phân giải hành vi truy cập field/method theo reference kind; kiểm tra các điều kiện phù hợp và tạo một `java.lang.invoke.MethodHandle`.
- **Dynamically-computed constant (`CONSTANT_Dynamic`):** bootstrap method tạo ra giá trị theo thông tin constant pool và tham số bootstrap. Sau khi resolve thành công, kết quả được giữ cho reference; bootstrap không tự chạy lại mỗi lần đọc constant đó.
- **Call site của `invokedynamic`:** JVM resolve bootstrap method, tham số và kết quả `CallSite`. Với loại này, resolution được gắn với **instruction `invokedynamic` cụ thể**, ngay cả khi nhiều instruction tham chiếu cùng entry constant pool.

Các ví dụ thực tế thường gặp là lambda expression và string concatenation hiện đại. Chi tiết phụ thuộc cách compiler sinh class file; source Java chứa `+` hoặc lambda **không đủ để khẳng định** lúc nào bootstrap được chạy. Dùng `javap -v` để xác định `InvokeDynamic` và `BootstrapMethods` của build thật.

Nếu bootstrap không hợp lệ hoặc thất bại, có thể gặp `BootstrapMethodError`. Những tình huống này là dynamic linking theo đặc tả JVM, không phải "reflection" thông thường.

## 5. Resolution diễn ra lúc nào? Một tham chiếu có phải được phân giải nhiều lần?

Trong một class đã được định nghĩa, JVM có thể phân giải symbolic reference trước khi lệnh dùng đến nó (eager) hoặc khi cần (lazy), trong giới hạn của JVMS. Một resolution thành công được ghi nhớ theo tham chiếu; nếu thất bại, lần sử dụng tham chiếu ấy tiếp tục gặp lỗi tương ứng. **Thời điểm phát hiện lỗi bên trong JVM có thể khác thời điểm lỗi trở nên quan sát được trong chương trình.** Thí nghiệm về thay phiên bản API ở trên minh họa hậu quả của binary incompatibility; bài kế tiếp đi sâu vào điểm xuất hiện lỗi khi eager/lazy resolution.

## 6. Thực hành A — xem symbolic references bằng `javap`

Tạo đúng cấu trúc tệp:

```text
resolution-lab/
└── src/
    └── demo/
        ├── Library.java
        └── Main.java
```

**Tệp `src/demo/Library.java`:**

```java
package demo;

public final class Library {
    public static int number = 7;

    static {
        System.out.println("Library initialized");
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp `src/demo/Main.java`:**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("start");

        Class<?> type = Library.class;
        System.out.println("literal=" + type.getName());

        System.out.println("before field");
        System.out.println("number=" + Library.number);
        System.out.println("call=" + Library.greet("Java"));
    }
}
```

Từ thư mục `resolution-lab`, biên dịch và chạy bằng JDK 17+:

```sh
javac --release 17 -d out src/demo/Library.java src/demo/Main.java
java -cp out demo.Main
```

**Stdout:**

```text
start
literal=demo.Library
before field
Library initialized
number=7
call=Hello, Java
```

Giải thích:

- `Library.class` là class literal: yêu cầu có biểu diễn `Class` tương ứng nhưng không phải active use kích hoạt `Library` initialization. Đừng suy ra từ đó thời điểm loading hoặc resolution bên trong JVM là chính xác tại dòng in nào.
- `Library.number` là **non-final static field**. `getstatic` cần tham chiếu field đúng và yêu cầu lớp khai báo field được initialized; vì vậy dòng `Library initialized` in **trước** `number=7`.
- `Library.greet("Java")` dùng `invokestatic`. Tại thời điểm này lớp đã khởi tạo, nên block static không chạy lại. Logic concat bên trong `greet` có thể dùng `invokedynamic` khi biên dịch bằng JDK 17.
- Thứ tự stdout phản ánh các **side effects quan sát được**; không chứng minh JVM thực hiện lazy resolution đúng ở một offset cụ thể.

Quan sát class file, không thay nội dung:

```sh
javap -classpath out -c -p demo.Main
javap -classpath out -v demo.Main
```

Trong `javap -c`, tìm lệnh tương ứng đọc field và gọi method:

```text
getstatic     ...  // Field demo/Library.number:I
invokestatic  ...  // Method demo/Library.greet:(Ljava/lang/String;)Ljava/lang/String;
```

Các dấu `...` đại diện cho chỉ số/offset do công cụ sinh ra, **không phải output nguyên văn đầy đủ**. Trong `javap -v`, mục `Constant pool` giải thích mỗi entry `Fieldref`, `Methodref`, `Class`, `NameAndType`. Các chỉ số `#n` có thể thay đổi khi sửa source, đổi compiler hoặc JDK. Bảng constant pool cho biết **điều gì cần được resolve**; nó không xác nhận thời điểm JVM đã thực hiện resolution khi chạy.

Để kiểm tra việc compiler loại bỏ một số tham chiếu, thử thay `Library.number` bằng `public static final int number = 7;` và biên dịch lại. Lúc này đây là **constant variable**, compiler thường inline giá trị ở nơi sử dụng, nên có thể không còn instruction `getstatic` cho lần đọc đó. Kiểm tra `javap` trước khi kết luận. Khi giá trị đã inline, đọc nó không yêu cầu khởi tạo `Library`, nhưng `greet` sau đó vẫn là active use.

## 7. Thực hành B — thay JAR runtime làm `NoSuchMethodError`

Đây là thí nghiệm về **binary compatibility**: compile dựa vào API phiên bản 1, rồi chạy với phiên bản 2 **không tương thích**. Không cần sửa bytecode thủ công.

Tạo ba source file riêng:

```text
resolution-compat/
└── src/
    ├── v1/
    │   └── api/
    │       └── Service.java
    ├── v2/
    │   └── api/
    │       └── Service.java
    └── client/
        └── demo/
            └── Client.java
```

**`src/v1/api/Service.java`:**

```java
package api;

public class Service {
    public static String version() {
        return "v1";
    }
}
```

**`src/v2/api/Service.java`:**

```java
package api;

public class Service {
    public static int version() {
        return 2;
    }
}
```

**`src/client/demo/Client.java`:**

```java
package demo;

import api.Service;

public class Client {
    public static void main(String[] args) {
        System.out.println("before");
        try {
            System.out.println(Service.version());
        } catch (NoSuchMethodError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
```

Từ thư mục `resolution-compat`, dùng JDK 17+:

```sh
javac --release 17 -d out-v1 src/v1/api/Service.java
javac --release 17 -cp out-v1 -d out-client src/client/demo/Client.java
javac --release 17 -d out-v2 src/v2/api/Service.java
```

Chạy đối chứng với API v1 trên **Windows PowerShell/CMD**:

```powershell
java -cp "out-client;out-v1" demo.Client
```

**Stdout đúng:**

```text
before
v1
```

Sau đó chạy với API v2 trên **Windows** (không cần biên dịch lại Client):

```powershell
java -cp "out-client;out-v2" demo.Client
```

**Stdout đúng:**

```text
before
NoSuchMethodError
```

Trên Linux/macOS, thay dấu `;` phân tách classpath bằng `:`, ví dụ `-cp "out-client:out-v2"`. Khi làm thí nghiệm, không đưa `out-v1` và `out-v2` lên cùng classpath: ta chủ ý chọn **một** bản `api.Service` tại runtime.

**Giải thích ở cấp JVM:**

1. Trong lúc compile `Client`, compiler thấy method `api.Service.version:()Ljava/lang/String;`.
2. Bytecode `Client.class` giữ symbolic method reference với **return type String**.
3. Khi chạy với `out-v2`, JVM có thể tìm class `api.Service` nhưng trong đó chỉ có `version:()I`.
4. Method reference cũ không tìm được method với tên và descriptor tương ứng; JVM báo `NoSuchMethodError` tại điểm sử dụng. `try/catch` trong bài bắt đúng lỗi để stdout gọn.
5. Sửa đúng là cung cấp bản API binary-compatible hoặc biên dịch lại client và mọi thành phần liên quan theo hợp đồng mới; đổi classpath một cách tình cờ có thể che giấu lỗi nhưng không giải quyết quản lý version.

Dùng các lệnh đọc bytecode để tự đối chiếu:

```sh
javap -classpath out-client -v demo.Client
javap -classpath out-v1 -s api.Service
javap -classpath out-v2 -s api.Service
```

Với `javap -s`, v1 chứa descriptor `()Ljava/lang/String;`, v2 chứa `()I`. Java ở mức source không cho khai báo hai method có cùng tên và cùng danh sách tham số chỉ khác return type trong cùng class; ví dụ này sử dụng hai bản build thay thế nhau, không phải overload hợp lệ.

## 8. Thực hành C — resolution không phải dynamic dispatch

Một lời gọi `invokeinterface` có thể resolve reference đến một method khai báo trong interface, rồi **method selection** chọn code dựa vào kiểu runtime của receiver.

Tạo **một** tệp `DispatchDemo.java` (các kiểu phụ không phải `public`, nên được phép cùng tệp):

```java
package demo;

interface Greeting {
    String say();
}

class EnglishGreeting implements Greeting {
    @Override
    public String say() {
        return "Hello";
    }
}

class VietnameseGreeting implements Greeting {
    @Override
    public String say() {
        return "Xin chao";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Greeting greeting = new EnglishGreeting();
        System.out.println(greeting.say());

        greeting = new VietnameseGreeting();
        System.out.println(greeting.say());
    }
}
```

Lưu trong `src/demo/DispatchDemo.java` của một thư mục thực hành riêng, rồi chạy:

```sh
javac --release 17 -d out src/demo/DispatchDemo.java
java -cp out demo.DispatchDemo
javap -classpath out -c demo.DispatchDemo
```

**Hai dòng stdout của lệnh `java`:**

```text
Hello
Xin chao
```

Lệnh `javap` phía sau sẽ in tiếp disassembly, không nằm trong hai dòng stdout trên. Trong mã `main`, hai lần gọi qua biến kiểu `Greeting` thường hiện thành `invokeinterface demo/Greeting.say:()Ljava/lang/String;`. Reference cấp interface giữ nguyên, nhưng instance đầu là `EnglishGreeting` còn instance sau là `VietnameseGreeting`; việc chọn method thực sự gọi phụ thuộc receiver. Có thể không có một "địa chỉ method duy nhất" dùng cho mọi instance sau khi interface reference đã resolved.

Điểm phân biệt:

- **Resolution:** `Greeting.say:()Ljava/lang/String;` là tham chiếu hợp lệ đến method của interface?
- **Selection:** Với object đang nhận lệnh gọi, implementation nào đáp ứng contract này?
- **Invocation:** JVM thực hiện method đã được chọn và trả kết quả.
- **Initialization:** Khởi tạo các lớp cần thiết xảy ra theo những trigger riêng khi tạo instance và gọi static members.

## 9. Class loader, runtime identity và loading constraints

Trong JVM, định danh của class/interface runtime dựa trên **cặp (binary name, defining loader)**. Hai plugin loaders có thể định nghĩa hai class `api.Dto` cùng tên nhưng **khác kiểu**. Resolution thông qua các loaders có thể nhận những định nghĩa runtime không tương thích dù source package giống nhau.

Ví dụ ý niệm:

```text
AppLoader      defines api.Dto (type A)
PluginLoader   defines api.Dto (type B)

api.Dto của AppLoader != api.Dto của PluginLoader
```

Khi liên kết field hoặc method có descriptor chứa các kiểu nằm ở biên giới loaders, JVM có thể áp dụng **loading constraints** để bảo đảm rằng cùng tên kiểu trong chữ ký của một liên kết buộc phải quy về cùng class/interface runtime. Nếu constraint bị vi phạm, có thể xuất hiện `LinkageError`. Điều này bảo vệ type safety, đặc biệt trong hệ thống plugin hoặc application server.

Dùng các điểm kiểm tra:

```java
Class<?> type = object.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Đây là đoạn **minh họa**, cần có biến `object` trong chương trình thực tế. Chú ý `getClassLoader() == null` thường mang nghĩa lớp được định nghĩa bởi **bootstrap loader**, không phải lỗi. Để tìm class cụ thể từ đâu, cần xem runtime module/classpath hoặc logging class loading cùng với thông tin defining loader.

**Module access:** Nếu type public nằm trong named module nhưng package không export cho module caller, symbolic resolution vẫn có thể thất bại vì quyền truy cập. "Có class file trên module path" chưa đủ.

**Ràng buộc phạm vi:** Nội dung trên nói về runtime linkage, khác với type erasure của generics và dependency injection của Spring. Đừng dùng từ "resolution" trong mọi thư viện để giả định nó có nghĩa giống JVM `5.4.3`.

## 10. Chẩn đoán lỗi: lỗi phát sinh ở bước nào?

| Triệu chứng | Tình huống thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | API `Class.forName`/`ClassLoader.loadClass` không tìm thấy tên yêu cầu | Tên đầy đủ, loader được dùng, JAR/classpath/module path; đây là checked exception của API tra cứu. |
| `NoClassDefFoundError` | Bytecode/runtime cần một class nhưng không thể định nghĩa/tìm thấy, hoặc lần initialization trước thất bại | Đọc thông điệp và `Caused by`; không đồng nhất mọi lỗi với class file thiếu. |
| `NoSuchFieldError` | Constant-pool `Fieldref` không khớp field runtime | Tên **và descriptor**; sự thay đổi kiểu field; phiên bản JAR thực tế. |
| `NoSuchMethodError` | `Methodref`/`InterfaceMethodref` không khớp runtime API | Tham số, return descriptor, binary incompatibility; thí nghiệm B. |
| `IllegalAccessError` | Truy cập kiểu/thành viên bị từ chối ở runtime | Quyền package/nest/module, dependency build khác runtime; khác `IllegalAccessException` của một số Reflection API. |
| `IncompatibleClassChangeError` | Dùng static/instance không tương thích hoặc thay đổi class/interface gây sai hợp đồng liên kết | Opcode caller, modifiers và bản API runtime. |
| `AbstractMethodError` | Lời gọi tới contract method nhưng không có implementation phù hợp tại runtime | Interface, implementation cũ, version lệch; có thể liên quan đến method selection/invocation. |
| `BootstrapMethodError` | Bootstrap cho dynamic constant/`invokedynamic` hỏng | `BootstrapMethods`, method handle, tham số bootstrap, root cause. |
| `VerifyError` | Bytecode không hợp lệ/không qua verification | Tool tạo/sửa class file, version bytecode, verification; khác trường hợp lookup thất bại. |
| `ExceptionInInitializerError` | Thực thi static initialization thất bại | Code `<clinit>`, giá trị static, nguyên nhân exception; khác resolution. |

`NoSuchMethodError`, `NoSuchFieldError` và một số lỗi trên thuộc họ **`LinkageError`** (nhiều lớp con cụ thể). Chúng thường xuất hiện sau khi **compile/runtime dependency lệch nhau**, nhưng không được suy ngược ngay rằng chỉ một nguyên nhân duy nhất. Kiểm tra stacktrace, nơi lỗi xảy ra và class loader thay vì thử thêm JAR không theo hệ thống.

Một lỗi như `NullPointerException` trong thân method là **lỗi khi thực thi chương trình**, không chứng minh resolution hỏng. Ngược lại, việc thấy `NoSuchMethodError` trước khi code method đích chạy là hợp lý: JVM chưa resolve được đích mà bytecode yêu cầu.

## 11. Quy trình debug resolution trong ứng dụng thực tế

1. **Xác định nơi gọi đang thất bại.** Lấy stacktrace đầu tiên và chain `Caused by`. Xác định bytecode của class caller (không chỉ nhìn source mới nhất).
2. **Đọc descriptor được yêu cầu.** Chạy `javap -classpath ... -v -c package.Caller`. Tìm `Fieldref`, `Methodref`, `InterfaceMethodref` gắn với opcode tại vị trí liên quan.
3. **Kiểm tra class runtime thật.** Dùng `javap -classpath ... -s package.Target` trên đúng JAR hoặc thư mục class mà ứng dụng đang chạy. So sánh descriptor, static/instance, access modifiers.
4. **Kiểm tra versions và đường nạp.** Xác minh thứ tự classpath, module path, fat JAR shading, plugin loaders, và package exports. Với Gradle/Maven, xem cây dependency runtime; tree compile không bảo đảm giống runtime.
5. **Tách loại lỗi.** `NoSuchMethodError` thường hướng vào binary mismatch; `IllegalAccessError` hướng vào access; `LinkageError` kèm loading-constraint violation hướng vào loader type identity; `ExceptionInInitializerError` hướng vào static initializer.
6. **Lặp lại với môi trường kiểm soát.** Tạo bản build sạch, xác định JDK, cùng classpath/module path; thêm log có chủ đích thay vì suy đoán thứ tự eager/lazy.
7. **Khắc phục ở nguồn.** Đồng bộ hợp đồng binary API/dependency, chỉnh exports/quyền truy cập hoặc hợp đồng plugin/shared loader; kiểm tra lại bằng cùng executable distribution dùng trong production.

Công cụ hữu ích trong JDK 17+:

```sh
javap -classpath out -v -c demo.Main
javap -classpath out -s demo.Library
java -Xlog:class+load=info -cp out demo.Main
```

`-Xlog:class+load=info` là Unified Logging của HotSpot/JDK hỗ trợ cờ này; log cho biết **loading events**, không phải danh sách chi tiết mọi lần resolution. JVM có tùy chọn logging khác tùy phiên bản/implementation; tránh tuyên bố rằng một dòng class-load chứng minh field/method đã resolved. `javap` đọc class file trên đĩa, không khẳng định chính tệp đó đã được class loader runtime lựa chọn nếu classpath thực tế khác.

Để so sánh caller và runtime target trong JAR:

```sh
javap -classpath app.jar -v -c com.example.app.Caller
javap -classpath dependency.jar -s com.example.lib.Target
```

Đây là **mẫu lệnh**; tên `app.jar` và class/package cần thay bằng artefact thực tế, không phải một ví dụ độc lập có output đã định.

## 12. Những nhầm lẫn cần tránh

- **"Loading hoàn tất thì tất cả symbolic references đã resolve."** Sai: các reference khác có thể vẫn chưa phân giải.
- **"Resolution luôn chạy sau preparation và trước mọi static initialization theo một đường thẳng duy nhất."** Không chính xác: cấu trúc linking có resolution, nhưng strategy eager/lazy khác nhau; JVM có thể tiếp tục phân giải sau initialization.
- **"Resolve method nghĩa là chọn method implementation cụ thể của object."** Sai với virtual/interface invocation: cần tách method resolution khỏi method selection.
- **"Class name đủ để tìm đúng type."** Sai với nhiều defining loaders; cặp tên/loader mới là định danh runtime.
- **"Đổi kiểu trả về method không ảnh hưởng caller nếu tên và tham số giữ nguyên."** Sai với bytecode: return type nằm trong JVM method descriptor.
- **"`javap` thấy `Methodref` thì method đã được execute."** Sai: `javap` chỉ cho biết metadata/static bytecode; resolution/execution là các sự kiện runtime.
- **"Mọi `LinkageError` đều do thiếu JAR."** Sai: có thể do method/field mismatch, access, loader constraints, class/interface mismatch, bootstrap error.
- **"Sửa file JAR tại chỗ đủ khiến class đang chạy tự relink."** Sai trong mô hình thông thường: class đã định nghĩa và kết quả resolution có quy tắc cache/thất bại; cần thay đúng runtime/deployment và thường khởi động lại hoặc tạo loader mới theo kiến trúc hợp lệ.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao compiler có thể tạo `Methodref` thay vì địa chỉ method?** Vì class file là định dạng độc lập môi trường, còn class/method runtime và class loader được xác định khi chương trình chạy.

**2. `getstatic` cần những bước nào?** Resolve field reference và thực hiện các kiểm tra liên kết thích hợp; khi cần, khởi tạo lớp/interface **khai báo field** trước khi đọc giá trị. Không đồng nhất hai cơ chế.

**3. Khi nào `NoSuchMethodError` xuất hiện dù `javac` từng thành công?** Khi bytecode caller tham chiếu method descriptor không còn được runtime class/interface đáp ứng; thường do binary-incompatible dependency.

**4. Hai `Class` cùng binary name có nhất thiết bằng nhau không?** Không. Nếu defining loader khác nhau thì là hai runtime types khác nhau.

**5. Một reference đã resolve sai có tự được tìm lại sau khi chép thêm JAR không?** Không thể dựa vào điều đó: JVMS ràng buộc kết quả/thất bại của lần resolution trước trên reference đó.

**6. Vì sao hai lời gọi `Greeting.say()` có hai output khác nhau?** Cùng symbolic interface method có thể được resolved, nhưng method selection lựa chọn implementation theo receiver runtime.

**7. `CONSTANT_InvokeDynamic` khác `Methodref` ở điểm nào đáng nhớ?** Resolution của call site động dùng bootstrap method và gắn kết quả với instruction `invokedynamic` cụ thể.

**8. Trong debugging, vì sao phải xem descriptor ngoài method name?** Vì JVM cần signature binary chính xác; cùng method name nhưng descriptor khác là reference khác.

## 14. Tài liệu chuẩn để kiểm chứng

- [The Java Virtual Machine Specification, Java SE 17 — 4: Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, `CONSTANT_*` và field/method descriptors.
- [The Java Virtual Machine Specification, Java SE 17 — 5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3): thời điểm resolution, kết quả thành công/thất bại, các loại reference.
- [The Java Virtual Machine Specification, Java SE 17 — 5.4.4 Access Control và 5.4.6 Method Selection](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): kiểm tra truy cập và lựa chọn method.
- [The Java Virtual Machine Specification, Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): phân biệt resolution với class initialization.

**Nguyên tắc nhớ:** resolution là việc JVM **liên kết tham chiếu ký hiệu của bytecode với thực thể runtime đúng, dưới đúng class loader và các quy tắc kiểm tra**. Loading tạo lớp; resolution nhận diện đích mà một tham chiếu yêu cầu; initialization chạy logic static khi cần; selection/invocation quyết định và thực thi phương thức phù hợp. Việc tách bốn cơ chế này là nền tảng để hiểu lỗi liên kết class, xung đột dependency và cách ly plugin trong Java.
