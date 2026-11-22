# `LinkageError` và các vấn đề tương thích mã đã biên dịch trong Java

Một chương trình Java có thể **biên dịch thành công** nhưng chỉ khi triển khai hoặc chạy đến một nhánh nhất định mới xuất hiện:

```text
java.lang.NoSuchMethodError
java.lang.NoSuchFieldError
java.lang.AbstractMethodError
java.lang.IncompatibleClassChangeError
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
java.lang.UnsupportedClassVersionError
```

Các lỗi này không đơn thuần có nghĩa “sai cú pháp Java”. Chúng thường chỉ ra rằng **bytecode được tạo trong một môi trường** đang được JVM **liên kết hoặc thực thi trong môi trường không còn đáp ứng các giả định về lớp, phương thức, trường, quyền truy cập hoặc phiên bản**.

`LinkageError` là một nhánh của `java.lang.Error`. Nó biểu diễn vấn đề trong **liên kết các lớp Java**: khi một lớp đã được biên dịch tham chiếu tới cấu trúc lớp khác, JVM cần tìm, xác minh, phân giải và sử dụng đúng cấu trúc đó tại runtime.

**Điểm cốt lõi:** *source compatibility*, *binary compatibility* và *runtime linkage* là ba khái niệm có liên quan nhưng **không đồng nghĩa**. Thay đổi source hợp lệ chưa chắc tương thích với client `.class` cũ; ngược lại, có thay đổi làm source cần sửa nhưng bytecode cũ vẫn chạy. Cần điều tra **artifact thực sự được chạy**, không chỉ mã nguồn mà IDE đang hiển thị.

## 1. `LinkageError` nằm ở đâu trong hệ ngoại lệ?

Sơ đồ rút gọn:

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── java.lang.RuntimeException
│   └── java.lang.ReflectiveOperationException
│       └── java.lang.ClassNotFoundException
└── java.lang.Error
    └── java.lang.LinkageError
        ├── java.lang.NoClassDefFoundError
        ├── java.lang.ExceptionInInitializerError
        ├── java.lang.ClassFormatError
        │   └── java.lang.UnsupportedClassVersionError
        ├── java.lang.VerifyError
        ├── java.lang.BootstrapMethodError
        ├── java.lang.UnsatisfiedLinkError
        └── java.lang.IncompatibleClassChangeError
            ├── java.lang.NoSuchMethodError
            ├── java.lang.NoSuchFieldError
            ├── java.lang.AbstractMethodError
            ├── java.lang.IllegalAccessError
            └── java.lang.InstantiationError
```

Đây là sơ đồ lựa chọn một số lớp quan trọng, không liệt kê hết hệ phân cấp. Cần đọc quan hệ cha/con thật, đặc biệt: `NoSuchMethodError` và `NoSuchFieldError` **không phải các sibling trực tiếp của `IncompatibleClassChangeError`**; chúng là **subclass** của nó.

| Thuộc tính | `LinkageError` và subclass |
| --- | --- |
| Gốc kế thừa | `Throwable → Error → LinkageError` |
| Checked exception? | **Không**; `Error` là unchecked |
| Lúc phát sinh | Khi JVM nạp/kiểm tra/liên kết/khởi tạo hoặc thực thi tham chiếu liên quan, tùy loại |
| Có được compiler buộc `catch`/`throws`? | Không |
| Có thể xảy ra sau khi ứng dụng đã chạy thành công một thời gian? | Có, do nhiều tham chiếu được phân giải hoặc lớp được khởi tạo theo nhu cầu |
| Nên mặc định bắt và bỏ qua? | Không; thường là vấn đề build, runtime, loader, compatibility hoặc class initialization cần sửa |

Đừng nhầm `LinkageError` với `ClassNotFoundException`: lỗi sau là **checked exception** thuộc nhánh `ReflectiveOperationException`, thường từ API tìm lớp theo tên. `NoClassDefFoundError` lại thuộc nhánh `LinkageError`. Hai loại có thể liên quan cùng một class bị thiếu nhưng phát sinh qua cơ chế khác nhau.

## 2. Loading, linking, initialization: không phải một bước duy nhất

Để hiểu các lỗi linkage, nên biết ba chặng lớn trong vòng đời lớp:

1. **Loading:** một class loader tìm hoặc định nghĩa biểu diễn của lớp theo tên.
2. **Linking:** gồm **verification**, **preparation** và **resolution**. JVM kiểm tra class file, chuẩn bị cấu trúc lớp và phân giải symbolic references theo quy tắc JVM.
3. **Initialization:** thực thi những static initializer và khởi tạo static field tương ứng khi lớp được chủ động sử dụng.

`LinkageError` có thể phản ánh nhiều điểm thất bại khác nhau trong quá trình này. Ví dụ:

- Không tìm được lớp cần thiết khi liên kết/sử dụng: có thể `NoClassDefFoundError`.
- Bytecode không hợp lệ hoặc không tương thích định dạng: có thể `ClassFormatError`/`VerifyError`.
- Runtime class còn tồn tại nhưng method ký hiệu trong bytecode cũ không còn: `NoSuchMethodError`.
- Lớp có static initialization thất bại: lần đầu có thể `ExceptionInInitializerError`, lần sử dụng tiếp có thể `NoClassDefFoundError`.
- Runtime class file được build cho Java mới hơn JVM đang chạy: `UnsupportedClassVersionError`.

### Resolution không nhất thiết xảy ra tất cả ở startup

JVM được phép phân giải nhiều symbolic references khi cần. Một nhánh code chưa được gọi có thể chưa kích hoạt lỗi. Bởi vậy:

- App khởi động và health check trả OK **không chứng minh** mọi binary dependency đã tương thích.
- Một endpoint hiếm dùng có thể lần đầu ném `NoSuchMethodError` khi có request sau nhiều ngày.
- Chạy unit test trên classpath khác production có thể không lộ được lỗi.
- Phân tích phải xét **phép gọi làm lỗi xuất hiện** và runtime artifact thực, không chỉ timestamp khởi động.

## 3. Source compatibility khác binary compatibility

**Source compatibility** hỏi: nếu biên dịch lại mã nguồn client cũ với thư viện mới, mã còn được compiler chấp nhận không?

**Binary compatibility** hỏi: nếu giữ nguyên file `Client.class` đã biên dịch với thư viện cũ, rồi thay bằng **binary thư viện mới**, bytecode client cũ có tiếp tục liên kết/sử dụng được theo các bảo đảm tương thích không?

**Behavioral compatibility** hỏi thêm: dù việc liên kết vẫn thành công, chương trình có còn thực hiện đúng ý nghĩa đã cam kết không?

Ba trục này không trùng nhau.

Ví dụ:

```java
// Thư viện phiên bản 1
public class PriceApi {
    public static int calculate() {
        return 100;
    }
}
```

Client gọi `PriceApi.calculate()`. Nếu thư viện phiên bản 2 **xóa phương thức** ấy hoặc thay chữ ký nhị phân theo cách không còn phương thức tương ứng, client `.class` cũ có thể ném `NoSuchMethodError` khi gọi.

Ngược lại, đổi **nội dung thân phương thức** từ trả `100` sang trả `120` mà vẫn giữ binary signature có thể không gây linkage error, nhưng vẫn phá **hành vi** nếu client dựa vào giá cũ. Không thể dùng việc “không có `LinkageError`” làm bằng chứng ứng dụng đúng nghiệp vụ.

### Symbolic reference là gì?

Java bytecode lưu tham chiếu theo **tên lớp, tên thành viên và descriptor của kiểu/chữ ký**. Khi thực thi một thao tác như gọi phương thức, JVM phân giải tham chiếu đó so với class thực trong runtime.

Điều này quan trọng khi client được biên dịch với một version của `LibraryApi` còn runtime thực tế chứa version khác: **source đang được mở trong IDE không quyết định bytecode runtime được phân giải ra sao**.

## 4. `NoSuchMethodError`: client cũ gọi phương thức không còn khớp

`NoSuchMethodError` xảy ra khi JVM không tìm được phương thức mà một tham chiếu nhị phân cần, sau các quy tắc phân giải liên quan.

Các thay đổi có thể dẫn tới lỗi:

- Xóa hoặc đổi tên method đã được client dùng.
- Đổi danh sách tham số, ví dụ `find(String)` thành `find(long)`.
- Đổi kiểu trả về trong binary descriptor mà không còn method tương ứng cho client cũ.
- Chạy client với một thư viện cũ hơn thư viện dùng khi compile (method mới không tồn tại).
- Runtime nạp **bản JAR khác** do classpath trùng dependency/transitive version conflict.

Ví dụ:

```java
// Client cũ đã biên dịch với API:
String value = LibraryApi.greet();
```

Nếu runtime `LibraryApi` không còn cung cấp `greet():String` như client kỳ vọng, có thể ném `NoSuchMethodError` tại điểm gọi.

**Đừng nhầm `NoSuchMethodError` với `NoSuchMethodException`**:

| `NoSuchMethodError` | `NoSuchMethodException` |
| --- | --- |
| Subclass của `IncompatibleClassChangeError` | Checked subtype của `ReflectiveOperationException` |
| Lỗi resolution/linkage của tham chiếu binary | Một lời gọi reflection không tìm được method theo truy vấn |
| Không buộc catch | Phải bắt/khai báo ở API reflection thích hợp |
| Thường cần sửa version/binary/deployment | Có thể là kết quả kiểm tra method tùy chọn theo reflection |

Chúng đều có từ “NoSuchMethod” nhưng **khác cơ chế và chính sách xử lý**.

## 5. Thí nghiệm Java 17+ hoàn chỉnh: tái tạo `NoSuchMethodError` bằng cách thay binary

Đây là thí nghiệm có kiểm soát. Bạn sẽ **biên dịch client cùng phiên bản thư viện v1**, rồi **chỉ thay class của thư viện bằng v2** mà **không biên dịch lại client**.

Tạo cấu trúc tệp trong một thư mục thí nghiệm riêng:

```text
binary-lab/
├── v1/
│   └── LibraryApi.java
├── v2/
│   └── LibraryApi.java
├── BinaryClient.java
└── build/            # thư mục đầu ra, có thể tạo bằng mkdir
```

**Tệp `v1/LibraryApi.java`:**

```java
public class LibraryApi {
    public static String greet() {
        return "hello-v1";
    }
}
```

**Tệp `v2/LibraryApi.java`:**

```java
public class LibraryApi {
    public static String salute() {
        return "hello-v2";
    }
}
```

Hai tệp có **cùng tên class binary** nhưng API khác nhau. Chúng không được biên dịch đồng thời làm hai bản định nghĩa `LibraryApi` trong cùng output.

**Tệp `BinaryClient.java`:**

```java
public class BinaryClient {
    public static void main(String[] args) {
        try {
            System.out.println(
                    "greeting=" + LibraryApi.greet());
        } catch (NoSuchMethodError ex) {
            System.out.println(
                    "linkage=" + ex.getClass().getSimpleName());
        }
    }
}
```

Tại thư mục `binary-lab`, chạy:

```bash
mkdir build
javac -encoding UTF-8 -d build v1/LibraryApi.java BinaryClient.java
java -cp build BinaryClient
```

**Stdout khi runtime còn v1:**

```text
greeting=hello-v1
```

Giờ **chỉ biên dịch file v2 vào cùng thư mục output**, ghi đè `build/LibraryApi.class` mà giữ nguyên `build/BinaryClient.class`:

```bash
javac -encoding UTF-8 -d build v2/LibraryApi.java
java -cp build BinaryClient
```

**Stdout sau khi thay binary:**

```text
linkage=NoSuchMethodError
```

Lệnh `javac` và `java` hoạt động tương tự trên POSIX shell và PowerShell; bạn có thể dùng `New-Item -ItemType Directory build` để tạo thư mục trong PowerShell nếu muốn. `mkdir build` chỉ cần chạy lần đầu khi thư mục chưa có.

### Giải thích chi tiết

1. `BinaryClient.java` chỉ có thể biên dịch vì v1 khai báo `LibraryApi.greet():String`.
2. Trong `BinaryClient.class` có tham chiếu tới method tương ứng.
3. Khi biên dịch v2 **chỉ với file `LibraryApi.java`**, JVM bytecode của client **không thay đổi**.
4. Khi chạy process mới, JVM tìm thấy `LibraryApi.class` của v2 nhưng class này chỉ có `salute()`, không còn `greet()`.
5. Khi client thực thi lời gọi cũ, JVM báo `NoSuchMethodError`. Handler ở đây chỉ để minh họa tên lỗi; không biến client cũ thành tương thích.

### Nếu biên dịch lại cả client với v2 thì sao?

Khi `BinaryClient.java` vẫn gọi `LibraryApi.greet()` mà v2 không có method, trình biên dịch sẽ báo lỗi source (ví dụ `cannot find symbol`) thay vì tạo ra cùng bytecode để runtime ném `NoSuchMethodError`. Đó là lý do thí nghiệm **cố tình giữ bytecode client cũ**.

**Không chạy thao tác thay thế `.class` trên project sản xuất.** Sử dụng riêng thư mục thí nghiệm để tránh phá build hiện có.

## 6. `NoSuchFieldError` và bẫy constant inlining

`NoSuchFieldError` giống `NoSuchMethodError` ở chỗ client binary cần một field mà runtime class không còn đáp ứng. Ví dụ:

```java
// v1
public class ConfigApi {
    public static int level = 3;
}
```

Client đã biên dịch đọc `ConfigApi.level`. Nếu v2 xóa field hoặc thay đổi định nghĩa sao cho tham chiếu binary cũ không còn được thỏa mãn, JVM có thể ném `NoSuchFieldError` lúc đọc field.

### Cẩn thận với `static final` compile-time constants

Đoạn sau là **constant variable**:

```java
public static final String LABEL = "v1";
```

Trong nhiều chỗ dùng, `javac` có thể **inline** giá trị `"v1"` vào client bytecode. Nếu sau đó xóa `LABEL` khỏi library, client cũ có thể **không** truy cập field runtime ở thao tác đó, nên **không nhất thiết ném `NoSuchFieldError`** mà vẫn hiển thị giá trị cũ.

Do đó, để minh họa `NoSuchFieldError` một cách đáng tin, ví dụ nên dùng **field không phải compile-time constant**.

## 7. Thí nghiệm Java 17+ hoàn chỉnh: thay binary để tạo `NoSuchFieldError`

Tạo thư mục riêng hoặc dùng một thư mục thí nghiệm khác với phần trước:

```text
field-lab/
├── v1/
│   └── FieldApi.java
├── v2/
│   └── FieldApi.java
├── FieldClient.java
└── build/
```

**Tệp `v1/FieldApi.java`:**

```java
public class FieldApi {
    public static final String CODE = new String("V1");
}
```

Dùng `new String("V1")` ở đây **chỉ nhằm tránh biến `CODE` thành compile-time constant**. Đây không phải khuyến nghị tạo `String` kiểu này trong ứng dụng thông thường.

**Tệp `v2/FieldApi.java`:**

```java
public class FieldApi {
    public static String currentCode() {
        return "V2";
    }
}
```

**Tệp `FieldClient.java`:**

```java
public class FieldClient {
    public static void main(String[] args) {
        try {
            System.out.println("field=" + FieldApi.CODE);
        } catch (NoSuchFieldError ex) {
            System.out.println(
                    "linkage=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch client với v1:

```bash
mkdir build
javac -encoding UTF-8 -d build v1/FieldApi.java FieldClient.java
java -cp build FieldClient
```

**Stdout với v1:**

```text
field=V1
```

Thay riêng binary của `FieldApi`:

```bash
javac -encoding UTF-8 -d build v2/FieldApi.java
java -cp build FieldClient
```

**Stdout với v2:**

```text
linkage=NoSuchFieldError
```

Tương tự thí nghiệm method, `FieldClient.class` giữ tham chiếu đã được biên dịch tới `FieldApi.CODE:Ljava/lang/String;`, trong khi runtime v2 không còn field này.

### Bài học về constant inlining

Nếu bạn thay trường v1 thành:

```java
public static final String CODE = "V1";
```

thì thí nghiệm có thể cho kết quả khác: compiler có thể inline literal `"V1"` vào client. Đây không phải bằng chứng mọi thay đổi field đều tương thích; nó cho thấy **bytecode thực sự đã được tạo** mới quyết định có tham chiếu runtime tới field hay không.

Có thể dùng `javap -c -p FieldClient` để thấy sự khác biệt giữa lệnh lấy field (`getstatic`) và constant được đưa thẳng vào bytecode trong những trường hợp compiler inline.

## 8. `IncompatibleClassChangeError`: sự thay đổi về “hình dạng” binary

`IncompatibleClassChangeError` có nhiều subclass cụ thể. Bản thân tên lỗi có thể xuất hiện khi bytecode mong đợi một thành viên hoặc kiểu có **hình dạng khác** thực tế.

Một ví dụ điển hình là **thay phương thức instance thành static** hoặc ngược lại trong bản thư viện runtime, trong khi giữ client binary cũ:

```java
// v1
public class ModeApi {
    public String status() {
        return "ready";
    }
}
```

Client được biên dịch dùng:

```java
new ModeApi().status();
```

Nếu v2 đổi method thành:

```java
// v2
public class ModeApi {
    public static String status() {
        return "ready";
    }
}
```

client cũ có thể vẫn chứa instruction gọi **instance method** theo hợp đồng v1. Khi runtime chỉ có method static tương ứng, JVM báo **`IncompatibleClassChangeError`** theo quy tắc invoke không phù hợp. Đây **không phải** một lời khuyên nên đổi static/instance kiểu này trong thư viện public.

### Thay `class` thành `interface`

Các phép gọi/kiểu liên quan tới class và interface được mã hóa và kiểm tra khác nhau. Đổi một public type từ class thành interface (hoặc ngược lại) mà client binary cũ vẫn kỳ vọng hình dạng trước đó có thể tạo linkage failure thuộc nhóm `IncompatibleClassChangeError`.

**Không thử sửa bằng cách ép kiểu hoặc thêm `throws`**. Phải khôi phục binary contract hoặc build lại toàn bộ thành phần phụ thuộc theo API mới.

## 9. `AbstractMethodError`: dispatch không tìm thấy triển khai phù hợp

`AbstractMethodError` xảy ra khi runtime cần gọi một abstract method nhưng không tìm được implementation concrete đáp ứng các quy tắc tương ứng.

Một tình huống cần chú ý trong nâng cấp API:

- Interface v1 công bố `run()`.
- Một implementation được build theo v1 thực hiện `run()`.
- Interface v2 thêm một **abstract method mới** `stop()`.
- Client mới được build để gọi `stop()`; runtime lại sử dụng implementation binary cũ chưa có method này.
- Khi thực thi lời gọi trên đối tượng implementation cũ, JVM có thể báo `AbstractMethodError`.

Khác biệt với `NoSuchMethodError`:

- Trong trường hợp này, interface/class contract mới **có khai báo method**, nhưng implementation runtime không đáp ứng lời gọi như một method concrete.
- Với `NoSuchMethodError`, tham chiếu nhị phân không được phân giải thành method cần thiết.

### Vì sao thêm abstract method có thể nguy hiểm?

Thêm method abstract vào một interface thường có ý nghĩa **người implement mới phải cài đặt**. Với mã nguồn cũ được build lại, compiler có thể yêu cầu bổ sung method. Nhưng các binary implementation cũ đã deploy có thể không được build lại ngay, tạo lỗi khi method mới được gọi.

Một cách phát triển API cần cân nhắc là dùng `default method` nếu có một hành vi mặc định đúng nghĩa:

```java
public interface Job {
    void run();

    default void stop() {
        throw new UnsupportedOperationException(
                "stop not supported");
    }
}
```

Đây là interface minh họa. `default` có thể giúp giảm yêu cầu triển khai khi nâng cấp trong một số trường hợp, **nhưng không bảo đảm mọi thay đổi interface đều nhị phân tương thích tuyệt đối**: nhiều kế thừa/default method xung đột và chi tiết resolution vẫn phải được đánh giá. Ngoài ra, `UnsupportedOperationException` là quyết định hành vi, không tự làm chức năng `stop` được hỗ trợ.

## 10. `IllegalAccessError`: binary tham chiếu không còn được phép truy cập

`IllegalAccessError` là subclass của `IncompatibleClassChangeError`, khác với checked reflection `IllegalAccessException`.

Ví dụ:

- Client được biên dịch khi một method của thư viện là `public`.
- Phiên bản thư viện runtime thay method ấy thành `private` hoặc giảm quyền truy cập theo cách không còn cho phép client gọi.
- Client binary vẫn cố truy cập như trước, dẫn tới `IllegalAccessError` khi resolution/access checking phát hiện sự không hợp lệ.

Một hệ thống sử dụng module cũng có thể gặp các ràng buộc truy cập ở những giai đoạn khác nhau. **Đừng gộp mọi lỗi mở package/reflection thành `IllegalAccessError`**: reflection có thể báo `IllegalAccessException` hoặc `InaccessibleObjectException` tùy thao tác và quy tắc JPMS.

Bảng so sánh:

| Loại | Nhóm | Ngữ cảnh |
| --- | --- | --- |
| `IllegalAccessError` | `LinkageError` → unchecked | JVM phát hiện một binary access không hợp lệ |
| `IllegalAccessException` | `ReflectiveOperationException` → checked | API reflection cố truy cập member không được phép trong tình huống tương ứng |
| `InaccessibleObjectException` | `RuntimeException` → unchecked | Reflection không thể mở quyền truy cập theo ràng buộc module/accessible flag |

Nếu lỗi xuất hiện sau nâng cấp library, hãy so sánh **quyền truy cập thực của member trong JAR runtime**, không chỉ mã nguồn version mới.

## 11. `NoClassDefFoundError`: lớp được tham chiếu nhưng runtime không dùng được

Một client đã biên dịch có thể chứa tham chiếu tới `com.example.Helper`. Nếu runtime class loader không tìm được định nghĩa cần thiết của `Helper`, JVM có thể ném `NoClassDefFoundError` tại lần sử dụng.

Khác với:

```java
Class.forName("com.example.Helper");
```

lời gọi `Class.forName` công bố checked `ClassNotFoundException` khi tìm lớp theo tên. Còn:

```java
Helper.doWork();
```

là **lời gọi minh họa** được biên dịch với tham chiếu trực tiếp tới class; nếu dependency runtime bị thiếu, có thể gặp `NoClassDefFoundError`.

Những nguyên nhân điển hình:

1. Một JAR có trên compile classpath nhưng vắng trên runtime classpath.
2. Dependency gián tiếp bị loại khỏi package/container image.
3. Class loader hiện tại không nhìn thấy class dù JAR ở nơi khác.
4. Class/module không được cung cấp trong cấu hình runtime phù hợp.
5. Lớp đã **thất bại ở static initialization** và được dùng lại.

`NoClassDefFoundError` không có nghĩa “Java không thể biên dịch file” và cũng **không luôn có nghĩa thiếu tệp `.class` vật lý**. Cần xét cả lỗi khởi tạo tĩnh.

### Cùng class name nhưng khác class loader

Danh tính runtime type phụ thuộc vào **binary name và defining class loader**. Hai class loader có thể định nghĩa lớp cùng tên nhưng JVM coi đó là hai kiểu runtime khác nhau. Hệ thống plugin/app server có thể có lỗi visibility/version do một loader nhìn thấy dependency mà loader khác không thấy.

Đừng chỉ kiểm tra `jar tf` cho thấy class hiện diện ở đâu đó rồi kết luận mọi loader đều dùng được class đó.

## 12. `ExceptionInInitializerError` và lớp ở trạng thái khởi tạo lỗi

Khi JVM khởi tạo class, nó chạy các static initializers theo quy tắc Java. Nếu quá trình đó ném một ngoại lệ không phải `Error` và không khởi tạo thành công, JVM có thể bọc lỗi bằng `ExceptionInInitializerError`.

Ví dụ:

```java
static final class Broken {
    static final int VALUE = initialize();

    static int initialize() {
        throw new IllegalStateException("bad startup config");
    }
}
```

Đây là nested class minh họa. Khi `Broken.VALUE` được đọc, JVM cần khởi tạo `Broken`, và phép gán static field làm ném `IllegalStateException`.

Sau thất bại, class có thể được đánh dấu **erroneous** đối với defining loader. Lần dùng tiếp theo trong cùng loader có thể ném `NoClassDefFoundError` với ý nghĩa lớp không thể khởi tạo, **dù class file vẫn tồn tại**.

### Ví dụ Java 17+ hoàn chỉnh: lỗi lần đầu và lần kế tiếp

Lưu tệp **`InitializationLinkageDemo.java`**:

```java
public class InitializationLinkageDemo {

    static final class Broken {
        static final int VALUE = initialize();

        static int initialize() {
            System.out.println("initializer invoked");
            throw new IllegalStateException(
                    "required configuration unavailable");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.VALUE);
        } catch (ExceptionInInitializerError ex) {
            System.out.println(
                    "first=" + ex.getClass().getSimpleName());
            System.out.println(
                    "cause=" + ex.getCause().getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.VALUE);
        } catch (NoClassDefFoundError ex) {
            System.out.println(
                    "second=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 InitializationLinkageDemo.java
java InitializationLinkageDemo
```

**Stdout dự kiến chính xác cho chương trình này:**

```text
initializer invoked
first=ExceptionInInitializerError
cause=IllegalStateException
second=NoClassDefFoundError
```

Phân tích:

- `Broken.VALUE` không phải compile-time constant vì giá trị đến từ lời gọi method.
- Lần truy cập đầu kích hoạt `initialize()`; method in một dòng rồi ném `IllegalStateException`.
- JVM bọc ngoại lệ đầu vào `ExceptionInInitializerError`; handler đọc `getCause()` là `IllegalStateException`.
- Lần đọc tiếp không chạy lại `initialize()`; JVM báo `NoClassDefFoundError` vì class đã khởi tạo thất bại trong cùng loader.

**Không sửa bằng cách retry không giới hạn.** Cần tìm lỗi khởi tạo **đầu tiên** trong log, sửa cấu hình/thứ tự startup, và dùng một process hoặc class loader mới theo cơ chế triển khai nếu phải chạy lại việc khởi tạo.

## 13. `UnsupportedClassVersionError`: phiên bản class file cao hơn runtime hỗ trợ

Một thư viện có thể được biên dịch bằng JDK mới hơn, trong khi production chạy JRE/JDK cũ hơn. JVM cũ không hiểu class-file major version của thư viện mới và có thể ném:

```text
java.lang.UnsupportedClassVersionError: ...
```

Đây là subclass của `ClassFormatError` → `LinkageError`.

Ví dụ người phát triển dùng JDK 21 để compile mặc định, nhưng máy chạy production chỉ có Java 17. File class tạo theo target mặc định của JDK 21 có thể không chạy trên Java 17.

Cách phòng:

```bash
javac --release 17 Example.java
```

Đây là **lệnh minh họa**, giả định `Example.java` tồn tại; `--release 17` yêu cầu compiler tạo class tương thích ngôn ngữ/API theo bản Java 17 được hỗ trợ bởi compiler.

**Không chỉ dùng `-source 17 -target 17` một cách tùy tiện nếu bạn cũng cần ràng buộc API thư viện chuẩn theo release đích**: `--release` được thiết kế để kiểm soát cả API public của Java platform theo target tương ứng.

### Class-file major version thường gặp

| Bản Java | Class-file major version |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Đây là các mốc ổn định. Một class file được biên dịch theo version cao hơn runtime có thể không dùng được; cũng cần xét preview features và các ràng buộc JVM tương ứng.

**Không đồng nhất `UnsupportedClassVersionError` với `NoClassDefFoundError`:** lỗi version có lớp/bytecode nhưng runtime **không hỗ trợ định dạng phiên bản**, không đơn giản là thiếu class.

## 14. `VerifyError` và `ClassFormatError`

`ClassFormatError` phát sinh khi file class không tuân thủ định dạng mà JVM hỗ trợ. Một số subclass biểu diễn vấn đề cụ thể, bao gồm `UnsupportedClassVersionError`.

`VerifyError` phát sinh khi JVM verifier phát hiện bytecode không thỏa các quy tắc xác minh cần thiết. Đây cũng là `LinkageError`.

Nguyên nhân có thể liên quan:

- Bytecode bị sửa/ghi sai bởi generator hoặc transformer.
- Tạo bytecode không hợp lệ theo quy tắc verifier.
- Agent/instrumentation hoặc build tooling tạo ra kết quả không phù hợp.
- Artifact bị hỏng hoặc kết hợp với công cụ bytecode không hỗ trợ phiên bản Java đang dùng.

Không kết luận rằng `VerifyError` luôn do một lỗi trong source code Java được `javac` biên dịch bình thường; phần lớn mã Java hợp lệ do compiler đáng tin tạo ra không chủ động sinh bytecode lỗi theo cách này.

Phân tích thực tế nên kiểm tra generator, bytecode instrumentation, phiên bản JVM và class file được nạp; nếu cần, tái tạo với build sạch và không có transform/agent để cô lập nguồn lỗi.

## 15. `BootstrapMethodError` và `invokedynamic`

Các tính năng JVM như `invokedynamic` sử dụng cơ chế bootstrap để liên kết các vị trí gọi động. Java lambda hoặc một số kiểu string concatenation có thể sử dụng những cơ chế bytecode liên quan.

`BootstrapMethodError` có thể phát sinh khi bootstrap method hoặc quá trình liên kết call site không hoàn tất đúng. Ví dụ nguồn lỗi có thể nằm ở:

- Một bootstrap method được tạo hoặc cấu hình sai.
- Sự không tương thích của bytecode được transform.
- Dependency runtime/lookup bị thay đổi làm bootstrap thất bại.
- Thao tác dynamic linkage phức tạp trong framework, compiler hoặc ngôn ngữ trên JVM khác.

Không nên suy ra **mọi lambda thất bại đều là `BootstrapMethodError`**. Lambda body ném `IOException`, `IllegalArgumentException` hoặc lỗi nghiệp vụ vẫn là ngoại lệ của logic tương ứng; bootstrap chỉ liên quan khi **liên kết call site** bị lỗi.

Nếu thấy `BootstrapMethodError`, hãy đọc cause, frame liên quan và dependency của công cụ sinh bytecode, thay vì chỉ sửa lambda body theo cảm tính.

## 16. `UnsatisfiedLinkError`: liên kết native library

`UnsatisfiedLinkError` cũng là subtype của `LinkageError`, nhưng liên quan **native code/JNI** hơn là một method Java bị xóa thông thường.

Các tình huống có thể gặp:

- `System.loadLibrary("native_component")` không tìm được native library thích hợp.
- Native binary sai kiến trúc hoặc không tương thích với hệ điều hành/ABI.
- Tên native method được khai báo ở Java không có implementation native tương thích.
- Thiếu dependency của chính native library.
- Đường tìm thư viện hoặc quyền truy cập native library không đúng.

Ví dụ:

```java
try {
    System.loadLibrary("definitely_missing_native_library");
} catch (UnsatisfiedLinkError ex) {
    System.out.println(
            "native=" + ex.getClass().getSimpleName());
}
```

Đây là **đoạn minh họa**, không đảm bảo cùng tên library sẽ thiếu ở mọi môi trường tùy chỉnh. Nó cho thấy lỗi native linkage không thuộc `ClassNotFoundException`.

Với hệ thống thật, kiểm tra kiến trúc CPU, `java.library.path`, loader của hệ điều hành, native dependencies, phiên bản JDK/JNI và cơ chế package native.

## 17. Các lỗi giống tên nhưng khác bản chất

| Lỗi | Khi nào thường gặp | Nhóm |
| --- | --- | --- |
| `NoSuchMethodException` | Reflection không tìm được method theo truy vấn | Checked exception |
| `NoSuchMethodError` | Binary method reference không còn được đáp ứng | `LinkageError` |
| `NoSuchFieldException` | Reflection không tìm được field theo truy vấn | Checked exception |
| `NoSuchFieldError` | Binary field reference không còn được đáp ứng | `LinkageError` |
| `ClassNotFoundException` | Nạp class theo tên qua API không thành công | Checked exception |
| `NoClassDefFoundError` | Runtime cần class definition không dùng được hoặc failed init | `LinkageError` |
| `IllegalAccessException` | Reflection access không được phép | Checked exception |
| `IllegalAccessError` | Binary access violation trong linkage | `LinkageError` |
| `ClassCastException` | Ép kiểu reference runtime sai | Unchecked `RuntimeException` |
| `IncompatibleClassChangeError` | Binary shape/dispatch không tương thích | `LinkageError` |
| `InvalidClassException` | Không tương thích Java object serialization theo hợp đồng | Checked `IOException` |

**Không phải mọi “lỗi version” đều là `LinkageError`.** Chẳng hạn `InvalidClassException` thường liên quan Java serialization và `serialVersionUID`/schema của object; đó là một checked I/O exception, không phải cơ chế JVM gọi method đã biên dịch không khớp.

## 18. Vì sao phụ thuộc cùng tên nhưng khác phiên bản gây linkage errors?

Một ứng dụng hiện đại có thể có:

- Mã ứng dụng.
- Nhiều thư viện trực tiếp.
- Thư viện bắc cầu (*transitive dependencies*).
- Plugin hoặc Java agents.
- Application server với thư viện dùng chung.
- Module path và classpath.
- JAR được đóng gói trong image/container.

Ví dụ mô hình:

```text
ServiceApp ───────► ReportingLibrary v3
     │                    │
     │                    └──► CommonApi v2
     │
     └────────────► LegacyConnector
                          └──► CommonApi v1
```

Nếu build compile một số client theo `CommonApi v2`, nhưng runtime class loader lại đưa `CommonApi v1` vào phạm vi trước, client có thể gọi method mới không tồn tại trong v1 → `NoSuchMethodError`.

Vấn đề không nhất thiết do một file `.class` “bị lỗi”; có thể là **version selection và class-loader visibility**.

### Không tin riêng file build khai báo

File cấu hình Maven/Gradle nói lên **ý định** dependency, không nhất thiết là toàn bộ artifact runtime. Cần xem:

- Dependency version **đã được resolve**.
- Phạm vi compile/runtime/test của từng dependency.
- Kết quả đóng gói (fat JAR, shaded JAR, WAR, distribution).
- Có JAR trùng class trong nhiều đường tìm không?
- Thư viện do container/app server cung cấp có đè phiên bản ứng dụng không?
- Class loader nào thật sự định nghĩa class lúc lỗi?

**Runtime truth = class bytes và class loader mà process thực đang sử dụng**, không chỉ dependency version được viết trong source configuration.

## 19. Dùng công cụ chuẩn để xem bytecode và classpath

### `java -version` và `javac -version`

```bash
java -version
javac -version
```

Kiểm tra JVM chạy thật và compiler đang dùng. Hai phiên bản có thể khác nhau trên cùng máy.

### `javap` để đọc signature và instruction

```bash
javap -classpath build -s -p LibraryApi
javap -classpath build -c -p BinaryClient
```

Trong thí nghiệm phần 5:

- `javap -s` có thể cho thấy descriptor của method runtime.
- `javap -c` có thể cho thấy bytecode của client còn tham chiếu tới `LibraryApi.greet`.
- Nếu đã thay `LibraryApi.class` bằng v2, công cụ có thể thấy class runtime không còn `greet` dù client binary vẫn gọi tên ấy.

Với phân tích phức tạp, `javap -v` cung cấp constant pool và dữ liệu class file chi tiết hơn.

### `jar tf` cho artifact thực

```bash
jar tf example-library.jar
```

Tìm entry như `com/example/LibraryApi.class`. Có tên class trong JAR mới chỉ chứng minh **artifact chứa entry**, không chứng minh app runtime nạp JAR đó, không chứng minh class phù hợp binary API.

### JVM unified logging cho class load

```bash
java -Xlog:class+load=info -cp build BinaryClient
```

Lệnh minh họa trên JVM hỗ trợ unified logging cho thấy nhiều sự kiện nạp lớp. Output dài, phụ thuộc JVM/version và môi trường, nên **không so khớp nguyên văn toàn bộ log** trong bài test.

### `jdeps` để xem dependencies

```bash
jdeps -verbose:class example-app.jar
```

`jdeps` giúp phân tích phụ thuộc tĩnh ở bytecode; nó không chứng minh mọi nhánh dynamic loading/reflection/plugin runtime đều đã được bao phủ.

### Maven/Gradle

Có thể dùng công cụ phân tích dependency graph của Maven/Gradle tương ứng với dự án đang dùng, rồi đối chiếu với JAR/thư mục thực của distribution. Cú pháp lệnh cụ thể phụ thuộc build tool và module configuration; không suy đoán một câu lệnh đúng cho mọi build.

## 20. Sửa lỗi bằng cách nào? Quy trình chẩn đoán tuần tự

### Bước 1 — Giữ nguyên loại lỗi thật

Nếu thấy `NoSuchMethodError`, đừng đổi thành một chuỗi lỗi chung “something failed”. Ghi lại:

- Lớp exception chính.
- Tên class và member liên quan nếu có.
- Chữ ký method/field mà client kỳ vọng khi có thể.
- Stack trace đầu tiên và `Caused by`, `Suppressed` nếu liên quan.
- Môi trường runtime: JDK, build ID, artifact và deployment version.

### Bước 2 — Xác định lời gọi gây lỗi

Frame nào trong mã ứng dụng đang gọi method/đọc field/kích hoạt class init?

- `NoSuchMethodError`: tìm method được gọi và binary descriptor.
- `NoSuchFieldError`: tìm field reference; xét compile-time constant inlining.
- `AbstractMethodError`: xem implementation concrete của interface/abstract class.
- `IllegalAccessError`: kiểm tra quyền truy cập member giữa các version.
- `NoClassDefFoundError`: kiểm tra class visibility, dependency hoặc failed initialization trước đó.

### Bước 3 — So sánh compile artifact với runtime artifact

Cần biết client `.class` được compile dựa trên phiên bản nào và JVM thật dùng JAR nào. Đọc dependency graph và class loading, không chỉ đoán từ tên package.

### Bước 4 — Kiểm tra phiên bản JVM

Nếu lỗi thuộc `UnsupportedClassVersionError`, kiểm tra class-file version, compiler target và runtime JDK. Đừng cố dùng `catch` để ép JVM hiểu bytecode mới hơn.

### Bước 5 — Phân biệt loader và module boundary

Với app server, plugin, JPMS hoặc custom `URLClassLoader`, xác định class được định nghĩa ở loader nào, liệu class có cùng binary name nhưng khác loader không, và module có nằm trong resolved graph không.

### Bước 6 — Cô lập bằng một build/runtime tối thiểu

Thí nghiệm v1/v2 ở trên là mô hình. Với dự án thật, tạo một integration test dùng **chính distribution** của hệ thống và các version đã chốt. Không tự sửa file `.class` trong production process đang chạy.

### Bước 7 — Áp dụng fix tại nguồn

Tùy nguyên nhân:

- Căn chỉnh dependency versions.
- Phục hồi public method/field binary contract hoặc cung cấp adapter tương thích.
- Build lại tất cả client nếu chủ động phá binary compatibility.
- Sửa runtime packaging/classpath/module path.
- Sửa static initializer và thứ tự cấu hình.
- Nâng đúng JVM hoặc compile target thấp hơn có hỗ trợ.
- Sửa agent/bytecode transformer nếu gây lỗi verify/bootstrap.

### Bước 8 — Kiểm chứng lại

Không chỉ kiểm tra app khởi động. Chạy **đúng code path từng gây lỗi**, và thêm regression/integration test cho bản artifact cuối cùng.

## 21. Khi nào nên giữ binary compatibility trong thư viện?

Nếu bạn phát hành một thư viện public, client có thể không được rebuild cùng lúc. Do đó một bản cập nhật nên có chiến lược:

- **Không xóa/đổi tên public method đang được sử dụng** nếu muốn giữ tương thích.
- Nếu API mới được thêm, cân nhắc **giữ method cũ** và delegation tới method mới trong giai đoạn chuyển tiếp.
- Không giảm access của public/protected member mà client cũ cần.
- Không đổi static/instance của field/method nếu client binary cũ chưa được cập nhật.
- Kiểm tra việc đổi class thành interface và ngược lại.
- Khi thêm abstract method vào interface, cân nhắc khả năng implementation cũ chưa rebuild.
- Xem xét binary/source tests với nhiều version của client và library.
- Có kế hoạch deprecation, migration và quản lý semantic versioning phù hợp.

### Bridge/delegation khi đổi API

Ví dụ thay vì xóa method cũ:

```java
public class LibraryApi {
    public static String greet() {
        return salute();
    }

    public static String salute() {
        return "hello-v2";
    }
}
```

Đây là **class minh họa**. Nếu các điều kiện class/loader khác vẫn tương thích, client binary cũ gọi `greet():String` có thể tiếp tục chạy, trong khi client mới dùng `salute()`.

Nhưng việc giữ tên **chưa đủ** nếu đã đổi return type, parameter types, static-ness, access hoặc các ràng buộc binary khác. Hãy kiểm tra descriptor và linkage thật.

## 22. “Rebuild tất cả” có phải cách sửa duy nhất?

Không phải lúc nào cũng cần rebuild toàn bộ. Có hai nhóm chiến lược:

**Giữ client binary cũ:**

- Phục hồi API tương thích trong library mới.
- Chọn đúng bản library mà client cần.
- Cài lại dependency thiếu/đúng version.
- Sửa class loader/deployment để JVM thấy artifact đúng.

**Chuyển sang API mới và cập nhật client:**

- Recompile/retest các client sau khi đổi signature.
- Phát hành artifact mới đồng bộ.
- Kiểm soát thời gian rollout nếu nhiều service/plugin cập nhật khác nhau.
- Có compatibility matrix giữa version producer/consumer.

Mục tiêu là **đảm bảo một runtime có bộ class và method phù hợp**, không chỉ tạo một bản build “không báo lỗi” trên môi trường phát triển.

### Cẩn thận với hot swap/hot reload

Việc thay JAR trên đĩa khi JVM đã chạy **không đảm bảo** các class được nạp trước sẽ tự đổi sang bytecode mới. Class đã được định nghĩa bởi loader thường giữ định nghĩa ấy trong vòng đời loader tương ứng; các cơ chế redefinition/reload có ràng buộc riêng.

Để kiểm chứng một phép nâng cấp binary, nên chạy **process sạch** hoặc dùng cơ chế plugin reload có kiểm soát, không đoán rằng thao tác thay file luôn có hiệu lực tức thì.

## 23. Liên hệ với checked exception và custom exceptions

Vì `LinkageError` là subclass của `Error`:

```java
try {
    runFeature();
} catch (Exception ex) {
    // Không bắt LinkageError.
}
```

Đây là mã minh họa với `runFeature()` được định nghĩa hợp lệ. `catch (Exception)` không bắt được `NoSuchMethodError`, `NoClassDefFoundError` hay các `LinkageError` khác.

Tương tự, thêm:

```java
void runFeature() throws NoSuchMethodError
```

là khai báo không cần thiết đối với compiler vì `NoSuchMethodError` là unchecked. Nó **không sửa** việc JVM không tìm được method.

### Khi nào có thể bắt một `LinkageError` cụ thể?

Trong ứng dụng thông thường, không nên bắt rồi coi tác vụ thành công. Nhưng một **plugin manager cách ly** có thể bắt một nhóm linkage errors ở ranh giới nạp plugin để:

1. Đánh dấu plugin không thể khởi động.
2. Báo lỗi có cấu trúc và giữ stack trace.
3. Không tiếp tục sử dụng đối tượng/class từ plugin lỗi.
4. Chọn plugin khác nếu hợp đồng cho phép và đã kiểm thử.
5. Không giấu lỗi của **core runtime dependency** như một lỗi plugin tùy chọn.

Đây là tình huống đặc thù, không phải quy tắc viết `catch (LinkageError ignored)` trên mọi API.

### Không phân loại theo `getMessage()`

Không nên:

```java
if (error.getMessage().contains("NoSuchMethod")) {
    // ...
}
```

Vì message có thể khác JVM/version và có thể `null`. Dùng **kiểu exception**, stack/cause và dữ liệu version/dependency được kiểm tra có cấu trúc. Ngay cả khi biết loại lỗi, **fix phải dựa vào binary mismatch thật**, không chỉ tên exception.

## 24. Lỗi khởi tạo khác lỗi missing method

Khi gặp:

```text
java.lang.NoClassDefFoundError: Could not initialize class ...
```

đừng chỉ tra xem `.class` ở JAR nào. Đây có thể là **hậu quả của một lần initialization failure trước đó**. Trình tự có thể như sau:

```text
Process khởi động
   |
   v
Lần đầu dùng ConfigHolder
   |
   +-- static initializer ném IllegalStateException
   |       -> ExceptionInInitializerError
   |
   v
Lần sau dùng ConfigHolder trong cùng loader
   |
   +-- NoClassDefFoundError
```

Nếu một công cụ giám sát chỉ giữ thông điệp lần sau mà bỏ log lần đầu, người vận hành có thể nhầm sang lỗi đóng gói classpath. Đây là lý do nên giữ **log theo sự kiện và cause chain**, không chỉ một message cuối.

## 25. Một số thay đổi API và rủi ro liên kết

| Thay đổi | Rủi ro điển hình với binary client cũ | Nhận xét |
| --- | --- | --- |
| Xóa public method đã dùng | `NoSuchMethodError` | Tham chiếu method cũ không còn |
| Đổi parameter/return descriptor | `NoSuchMethodError` hoặc linkage failure tương ứng | Binary descriptor là yếu tố then chốt |
| Xóa field đã dùng | `NoSuchFieldError` | Constant inlining có thể làm vài call site khác biệt |
| Instance method ↔ static method | `IncompatibleClassChangeError` | Instruction invoke và loại member không khớp |
| Giảm access của member | `IllegalAccessError` | Kiểm tra quyền JVM ở runtime |
| Thêm abstract interface method rồi gọi trên implementation cũ | `AbstractMethodError` | Implementation cũ không có method concrete |
| Loại class khỏi runtime dependency | `NoClassDefFoundError` | Không phải trường hợp duy nhất gây NCDFE |
| Static initializer thất bại | `ExceptionInInitializerError`, sau đó có thể `NoClassDefFoundError` | Tìm lỗi gốc lần đầu |
| Class file build cho JDK quá mới | `UnsupportedClassVersionError` | Fix target/runtime JDK |
| Bytecode generator tạo class lỗi định dạng | `ClassFormatError`/`VerifyError` | Cần sửa tooling/artifact |
| Bootstrap linkage không thành công | `BootstrapMethodError` | Điều tra bootstrap/cause |
| Native library không load/link được | `UnsatisfiedLinkError` | Không phải lỗi public method Java bị xóa |

Bảng thể hiện **rủi ro thường gặp**, không phải hàm ánh xạ một-một cho mọi biến thể của đặc tả. Có thay đổi tương thích hơn bạn tưởng, có thay đổi source-compatible nhưng không phù hợp binary, và có các trường hợp JVM chọn subclass cụ thể theo chặng lỗi.

## 26. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách sửa |
| --- | --- | --- |
| “Biên dịch thành công thì chắc chắn runtime có đủ method” | Runtime class có thể là bản khác | Kiểm tra artifact và version thực |
| “Mọi lỗi linkage đều do thiếu JAR” | Có method/field/access/initialization/bytecode version | Phân loại subtype |
| “`NoSuchMethodError` là checked exception” | Nó extends `Error` | Sửa binary contract, không thêm `throws` |
| “`NoSuchMethodException` và `NoSuchMethodError` như nhau” | Reflection vs binary linkage | Đọc đúng hierarchy |
| “Nếu `jar tf` thấy class thì JVM chắc dùng được” | Class loader, module, dependency, init còn ảnh hưởng | Kiểm tra actual class loader |
| “Có `NoClassDefFoundError` nghĩa là file class luôn bị xóa” | Failed static init cũng tạo lỗi này | Tìm `ExceptionInInitializerError` đầu tiên |
| “Catch `Exception` sẽ bắt mọi linkage error” | `Error` nằm ngoài nhánh `Exception` | Xem đúng cơ chế |
| “Catch `Throwable` và trả default sẽ phục hồi” | Dễ che deployment hỏng | Fail/report ở ranh giới phù hợp |
| “Xóa `static final String` luôn gây `NoSuchFieldError`” | Constant có thể bị inline | Xem bytecode thực |
| “Cứ rebuild client là đủ” | Nếu runtime vẫn sai JAR, lỗi vẫn có thể còn | Sửa package/deploy classpath |
| “`java -version` trùng máy build” | CI, IDE, container, service có thể khác runtime | Đọc process thực |
| “Thay JAR trên đĩa thay bytecode trong JVM” | Class đã nạp không tự thay theo file | Restart/reload đúng cơ chế |
| “Không có linkage error nghĩa là API tương thích hành vi” | Semantics có thể đổi dù binary hợp lệ | Test hành vi và contract |
| “`NoSuchFieldError` luôn xuất hiện ngay khi startup” | Resolution có thể lười | Test code path gây lỗi |
| “Class loader nào cũng nhìn cùng một class” | Visibility và type identity theo defining loader | Phân tích loader |
| “`UnsupportedClassVersionError` do method bị xóa” | Class-file format version không được JVM hỗ trợ | Sửa `--release`/runtime |

## 27. Bài tập tự kiểm tra

**Câu A.** `NoSuchMethodError` thuộc `Exception` hay `Error`?

**Đáp án:** thuộc `IncompatibleClassChangeError` → `LinkageError` → `Error`, là unchecked.

**Câu B.** Client được compile với thư viện v1 có `greet()`. Runtime v2 xóa `greet()`, client `.class` cũ vẫn chạy. Khi gọi method cũ có thể gặp gì?

**Đáp án:** `NoSuchMethodError`.

**Câu C.** Vì sao build lại client với v2 có thể báo lỗi compile-time thay vì `NoSuchMethodError` runtime?

**Đáp án:** source client gọi method không có trong API mới, nên `javac` không tạo ra bytecode hợp lệ với lời gọi ấy. Lỗi runtime tái hiện khi **giữ client bytecode cũ**.

**Câu D.** Đổi static method thành instance có liên quan gì đến `IncompatibleClassChangeError`?

**Đáp án:** bytecode cũ có thể sử dụng loại invocation dành cho static trong khi runtime member là instance, hoặc ngược lại. Đây là mismatch về binary shape.

**Câu E.** Vì sao không nên dùng `public static final String NAME = "x"` trong thí nghiệm chắc chắn tạo `NoSuchFieldError`?

**Đáp án:** biến là compile-time constant và giá trị có thể được inline vào bytecode client, khiến lần đọc không còn thực hiện `getstatic` ở runtime.

**Câu F.** Thêm abstract method vào interface v2 nhưng vẫn dùng implementation binary v1. Khi client mới gọi method đó có thể gặp gì?

**Đáp án:** `AbstractMethodError` nếu runtime dispatch không có implementation concrete phù hợp.

**Câu G.** Static initializer ném `IllegalStateException` lần đầu, sau đó cùng lớp được dùng lại. Hai lỗi nào thường xuất hiện?

**Đáp án:** lần đầu `ExceptionInInitializerError`, lần sau có thể `NoClassDefFoundError`.

**Câu H.** Java 21 compile mặc định, Java 17 chạy class file đó. Loại lỗi nào cần xem xét?

**Đáp án:** `UnsupportedClassVersionError` nếu class file target vượt khả năng JVM 17.

**Câu I.** Một JAR đúng tên chứa `SomeApi.class` nhưng runtime vẫn có lỗi method. Tại sao?

**Đáp án:** có thể class đã được nạp từ **JAR khác hoặc loader khác**, hoặc JAR chứa class nhưng binary API không có method descriptor mà client cần.

**Câu J.** Reflection gọi `getDeclaredMethod("missing")` và không tìm được method. Có bắt buộc là `NoSuchMethodError` không?

**Đáp án:** không; API reflection khai báo checked `NoSuchMethodException`.

**Câu K.** `catch (Exception)` có bắt `VerifyError` không?

**Đáp án:** không, `VerifyError` là `LinkageError`, không extends `Exception`.

**Câu L.** Thay đổi body method nhưng giữ cùng binary signature có nhất thiết tạo linkage error không?

**Đáp án:** không. Nó có thể tương thích binary nhưng thay đổi hành vi, nên vẫn phải test nghiệp vụ.

**Câu M.** Thay JAR trên filesystem sau khi class đã được JVM nạp có bảo đảm JVM dùng định nghĩa mới ngay không?

**Đáp án:** không. Cần hiểu vòng đời defining loader và cơ chế reload/redefinition đang dùng.

**Câu N.** `ClassNotFoundException` và `NoClassDefFoundError` khác nhau thế nào?

**Đáp án:** CNFE là checked exception thường từ API tìm lớp theo tên, còn NCDFE là unchecked linkage error khi JVM cần định nghĩa lớp runtime hoặc gặp class ở trạng thái failed initialization.

**Câu O.** Lúc service mới khởi động không có lỗi, một API ít dùng sau ba ngày ném `NoSuchMethodError`. Điều đó có mâu thuẫn không?

**Đáp án:** không. JVM có thể phân giải tham chiếu khi code path ấy chạy lần đầu. Cần kiểm tra runtime class bytes tại thời điểm lỗi.

## 28. Checklist phát hành thư viện và triển khai

Trước khi phát hành một API Java public:

1. Kiểm tra class/method/field **binary signatures** trước và sau.
2. Xác định những client không được rebuild cùng bản library.
3. Giữ các entrypoint public cũ hoặc cung cấp compatibility bridge nếu có thể.
4. Tránh thay đổi static/instance/access không tương thích.
5. Cân nhắc interface implementations cũ trước khi thêm abstract method.
6. Không coi compile-time constants là cơ chế versioning động đáng tin.
7. Kiểm tra tương thích nguồn, nhị phân và hành vi tách biệt.
8. Cài regression test chạy **client build với bản cũ + library runtime bản mới** khi cần hứa binary compatibility.

Trước khi triển khai ứng dụng:

1. Chốt dependency graph/resolved versions.
2. Xác nhận runtime distribution chứa dependency bắt buộc.
3. Kiểm tra classpath/module path và các JAR trùng tên class.
4. Xác nhận JDK version thực và compiler release target.
5. Xác định class loader/plugin boundaries.
6. Test artifact cuối cùng, không chỉ test trong IDE.
7. Tránh static initialization nặng, khó kiểm soát và phụ thuộc môi trường.
8. Có giám sát phát hiện `LinkageError` và lưu cause/log của lỗi đầu.
9. Khi lỗi xuất hiện, không tự retry vô hạn hoặc trả success giả.
10. Sau khi sửa dependency, restart/reload theo cơ chế runtime hợp lệ và chạy lại chính code path từng lỗi.

## Kết luận

**`LinkageError` là nhóm lỗi về việc runtime JVM không thể liên kết hoặc sử dụng một số cấu trúc đã được mã biên dịch giả định.** Những subclass như `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` và `IllegalAccessError` thường liên quan **binary API không còn khớp**; `NoClassDefFoundError` có thể liên quan class thiếu hoặc khởi tạo thất bại; `UnsupportedClassVersionError`, `VerifyError`, `BootstrapMethodError` hay `UnsatisfiedLinkError` có cơ chế riêng cần điều tra đúng.

Để tránh và xử lý nhóm lỗi này, hãy phân biệt **compile-time source**, **client bytecode**, **library bytecode runtime**, **class loader/module graph** và **trạng thái khởi tạo lớp**. Khi nâng cấp thư viện, đừng chỉ hỏi “build có xanh không?” mà hãy hỏi **binary client cũ còn liên kết và chạy đúng hợp đồng với library mới không?**. Khi sự cố xảy ra, giải pháp bền vững thường là **căn chỉnh artifact, phiên bản JDK, classpath, binary contract hoặc cơ chế khởi tạo**, chứ không phải catch `Error` rồi cho qua.