# Xem private member bằng javap

Trong Java, các thành viên của lớp có thể được khai báo với nhiều mức truy cập: `public`, `protected`, package-private (không ghi modifier) và `private`. Khi kiểm tra một thư viện hoặc tệp `.class`, đôi khi cần xem cả những field và method không được công khai.

Công cụ **`javap`** của JDK hỗ trợ việc này bằng tùy chọn `-p` hoặc `-private`. Tùy chọn này yêu cầu hiển thị tất cả thành viên được khai báo trong class file, bao gồm cả thành viên private.

## 1. Vì sao cần xem private member?

Theo nguyên tắc đóng gói (encapsulation), lớp thường giữ dữ liệu và thao tác nội bộ ở phạm vi private, chỉ cung cấp một API công khai cho mã bên ngoài.

Ví dụ:

```java
public class User {
    private String password;
    private boolean active;

    public boolean isActive() {
        return active;
    }
}
```

Mã nguồn bên ngoài lớp có thể gọi `isActive()`, nhưng không thể truy cập trực tiếp `password` theo quy tắc truy cập Java thông thường.

Khi phân tích class file, việc chỉ xem API public có thể chưa đủ. Bạn có thể cần biết:

- Lớp có những field private nào.
- Có method private nào thực hiện xử lý nội bộ.
- Constructor và các method overload được khai báo ra sao.
- Kiểu dữ liệu, tham số và kiểu trả về của thành viên.
- Thành viên có cờ `static`, `final`, `volatile`, `synchronized` hay các cờ đặc biệt khác không.
- Compiler có sinh thêm bridge method hoặc synthetic member không.

`javap -p` giúp quan sát metadata này mà không cần mã nguồn gốc.

## 2. Tùy chọn -p và -private

Hai cách viết sau có cùng mục đích:

```bash
javap -p ClassName
javap -private ClassName
```

`-p` là dạng viết ngắn của `-private`. Tùy chọn này yêu cầu `javap` hiển thị mọi field và method được khai báo trong lớp, bất kể mức truy cập.

Nếu không dùng `-p`, `javap` mặc định hiển thị các thành viên public và protected. Thành viên private và package-private sẽ không được hiển thị trong chế độ mặc định.

Các tùy chọn liên quan:

| Tùy chọn | Phạm vi thành viên được hiển thị |
| --- | --- |
| `-public` | Chỉ public |
| `-protected` | Public và protected; đây là chế độ mặc định |
| `-package` | Public, protected và package-private |
| `-private` hoặc `-p` | Tất cả thành viên, bao gồm private |

Ví dụ:

```bash
javap -classpath out -p User
```

Lệnh tìm lớp `User` trong thư mục `out` và hiển thị cả các thành viên private.

**Lưu ý:** `-p` điều khiển cách `javap` hiển thị nội dung class file. Nó không thay đổi modifier trong class file, không sửa bytecode và không cấp quyền truy cập private cho chương trình Java khác.

## 3. Chuẩn bị ví dụ có private member

Tạo tệp **`PrivateMemberDemo.java`**:

```java
public class PrivateMemberDemo {
    private String name;
    private static final int MAX_RETRIES = 3;

    String state = "READY";
    protected int retryCount;

    public PrivateMemberDemo(String name) {
        this.name = normalize(name);
    }

    private String normalize(String value) {
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }

    private static boolean isValid(String value) {
        return value != null && !value.isEmpty();
    }

    public String getName() {
        return name;
    }

    void reset() {
        retryCount = 0;
        state = "READY";
    }

    protected void incrementRetry() {
        if (retryCount < MAX_RETRIES) {
            retryCount++;
        }
    }

    public static void main(String[] args) {
        PrivateMemberDemo demo = new PrivateMemberDemo("Java");
        System.out.println(demo.getName());
        System.out.println(isValid("Java"));
    }
}
```

Lớp có nhiều loại thành viên:

| Thành viên | Mức truy cập | Loại |
| --- | --- | --- |
| `name` | private | Field instance |
| `MAX_RETRIES` | private | Field static final |
| `state` | package-private | Field instance |
| `retryCount` | protected | Field instance |
| `normalize(String)` | private | Method instance |
| `isValid(String)` | private static | Method static |
| `getName()` | public | Method instance |
| `reset()` | package-private | Method instance |
| `incrementRetry()` | protected | Method instance |
| `main(String[])` | public static | Method static |

Biên dịch ví dụ bằng JDK:

```bash
javac -g -parameters -d out PrivateMemberDemo.java
```

- `-g` yêu cầu lưu thông tin debug như số dòng và biến cục bộ.
- `-parameters` yêu cầu lưu tên tham số method trong metadata phù hợp.
- `-d out` đặt thư mục gốc cho class file đầu ra.

Sau khi biên dịch, tệp được tạo tại:

```text
out/
  PrivateMemberDemo.class
```

## 4. So sánh kết quả trước và sau khi dùng -p

### Chế độ mặc định

Chạy:

```bash
javap -classpath out PrivateMemberDemo
```

Kết quả minh họa:

```text
Compiled from "PrivateMemberDemo.java"
public class PrivateMemberDemo {
  protected int retryCount;
  public PrivateMemberDemo(java.lang.String);
  public java.lang.String getName();
  protected void incrementRetry();
  public static void main(java.lang.String[]);
}
```

Các thành viên private như `name`, `MAX_RETRIES`, `normalize()` và `isValid()` không xuất hiện. Thành viên package-private như `state` và `reset()` cũng không xuất hiện trong chế độ mặc định.

### Hiển thị tất cả thành viên

Chạy:

```bash
javap -classpath out -p PrivateMemberDemo
```

Kết quả minh họa:

```text
Compiled from "PrivateMemberDemo.java"
public class PrivateMemberDemo {
  private java.lang.String name;
  private static final int MAX_RETRIES;
  java.lang.String state;
  protected int retryCount;
  public PrivateMemberDemo(java.lang.String);
  private java.lang.String normalize(java.lang.String);
  private static boolean isValid(java.lang.String);
  public java.lang.String getName();
  void reset();
  protected void incrementRetry();
  public static void main(java.lang.String[]);
}
```

Bây giờ có thể thấy cả private field, private method và thành viên package-private. Thứ tự hiển thị hoặc một số chi tiết định dạng có thể thay đổi theo phiên bản JDK; hãy đối chiếu tên, descriptor và cờ truy cập thay vì phụ thuộc tuyệt đối vào thứ tự dòng.

## 5. Xem descriptor của private member

Để xem chữ ký kiểu ở định dạng JVM, kết hợp `-p` với `-s`:

```bash
javap -classpath out -p -s PrivateMemberDemo
```

Tùy chọn:

- `-p`: hiển thị cả thành viên private.
- `-s`: hiển thị descriptor của field và method.

Ví dụ, một số descriptor của lớp:

| Thành viên Java | Descriptor |
| --- | --- |
| `private String name;` | `Ljava/lang/String;` |
| `private static final int MAX_RETRIES;` | `I` |
| `private String normalize(String value)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `private static boolean isValid(String value)` | `(Ljava/lang/String;)Z` |
| `PrivateMemberDemo(String name)` (constructor) | `(Ljava/lang/String;)V` |

Tên tham số không nằm trong descriptor. Descriptor method gồm kiểu tham số trong ngoặc đơn, sau đó là kiểu trả về. Ký hiệu `V` biểu diễn `void`.

Khi kiểm tra thư viện đã biên dịch, descriptor giúp phân biệt các method overload và xác định chính xác kiểu mà JVM sử dụng khi liên kết method.

## 6. Xem bytecode bên trong private method

Private method cũng có bytecode như các method Java thông thường có phần thân. Dùng `-c` để xem lệnh bytecode:

```bash
javap -classpath out -p -c PrivateMemberDemo
```

Trong output, tìm phần:

```text
private java.lang.String normalize(java.lang.String);
  Code:
     ...
```

Tùy chọn `-p` làm cho method private xuất hiện; `-c` hiển thị bytecode của nó.

Đối với method `normalize`, bytecode thực hiện các thao tác tương ứng với:

1. Nhận tham số kiểu String.
2. Gọi `trim()`.
3. Gọi `toUpperCase(Locale.ROOT)`.
4. Trả về chuỗi kết quả.

Các lệnh cụ thể và offset có thể khác nhau giữa các bản JDK. Nếu cần xem lời gọi method, local variable và operand stack, hãy đọc phần `Code` của method trong output disassembly.

## 7. Xem access flags và metadata chi tiết

Để xem đầy đủ access flags, descriptor, constant pool và attributes, chạy:

```bash
javap -classpath out -p -v PrivateMemberDemo
```

Một field private có thể được hiển thị tương tự:

```text
private java.lang.String name;
  descriptor: Ljava/lang/String;
  flags: ACC_PRIVATE
```

Một method private instance có thể có:

```text
private java.lang.String normalize(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: ACC_PRIVATE
```

Method private static có thể có tổ hợp cờ:

```text
private static boolean isValid(java.lang.String);
  descriptor: (Ljava/lang/String;)Z
  flags: ACC_PRIVATE, ACC_STATIC
```

Một số cờ thường gặp:

| Access flag | Ý nghĩa |
| --- | --- |
| `ACC_PRIVATE` | Thành viên có mức truy cập private |
| `ACC_PROTECTED` | Thành viên có mức truy cập protected |
| `ACC_PUBLIC` | Thành viên có mức truy cập public |
| `ACC_STATIC` | Thành viên thuộc lớp |
| `ACC_FINAL` | Thành viên mang đặc tính final |
| `ACC_SYNCHRONIZED` | Method có ngữ nghĩa đồng bộ hóa |
| `ACC_BRIDGE` | Method bridge do compiler sinh ra |
| `ACC_SYNTHETIC` | Thành viên được compiler sinh ra |

Với field `MAX_RETRIES`, có thể kết hợp tùy chọn `-constants` để xem giá trị hằng phù hợp:

```bash
javap -classpath out -p -constants PrivateMemberDemo
```

Kết quả có thể hiển thị:

```text
private static final int MAX_RETRIES = 3;
```

Không phải mọi field `final` đều có giá trị ConstantValue trong class file. Các giá trị cần được tính toán trong lúc chạy có thể được thiết lập bằng bytecode khởi tạo.

## 8. Kiểm tra private member trong JAR

Không cần giải nén thư viện JAR chỉ để xem khai báo của một lớp. Có thể chỉ định JAR làm classpath và dùng tên đầy đủ của lớp.

Ví dụ, nếu thư viện có lớp `com.example.internal.TokenStore`:

```bash
javap -classpath lib/example.jar -p com.example.internal.TokenStore
```

Xem descriptor và bytecode:

```bash
javap -classpath lib/example.jar -p -s -c com.example.internal.TokenStore
```

Nếu có nhiều JAR phụ thuộc, truyền danh sách classpath theo hệ điều hành:

**Windows:**

```powershell
javap -classpath "lib\example.jar;lib\common.jar" -p com.example.internal.TokenStore
```

**macOS/Linux:**

```bash
javap -classpath "lib/example.jar:lib/common.jar" -p com.example.internal.TokenStore
```

Classpath phải trỏ đến JAR chứa lớp cần kiểm tra. Nếu lớp nằm trong package, hãy dùng tên đầy đủ với dấu chấm, ví dụ `com.example.internal.TokenStore`.

## 9. Kiểm tra private member của inner class

Một lớp lồng bên trong (nested class) có class file riêng. Ví dụ:

```java
public class Outer {
    private static class Secret {
        private String value = "hidden";

        private String read() {
            return value;
        }
    }
}
```

Compiler tạo class file có tên nhị phân tương tự:

```text
Outer.class
Outer$Secret.class
```

Có thể kiểm tra thành viên private của lớp lồng bằng:

```bash
javap -classpath out -p 'Outer$Secret'
```

Dấu nháy giúp shell không diễn giải ký tự `$` như biến môi trường hoặc biến shell. Tên lớp nhị phân dùng dấu `$` để phân biệt lớp lồng với lớp bên ngoài.

Nếu cần xem thành viên private của cả lớp ngoài và lớp lồng, chạy `javap -p` riêng cho từng class file.

## 10. javap -p không làm thay đổi quyền truy cập

Điều quan trọng là phân biệt **xem metadata** với **truy cập thành viên khi chương trình chạy**.

`javap -p` chỉ đọc thông tin trong class file và hiển thị những thành viên vốn đã được khai báo. Nó không:

- Chuyển private thành public.
- Sửa access flags hoặc bytecode.
- Cho phép mã nguồn khác gọi trực tiếp private method.
- Bỏ qua kiểm tra truy cập của compiler hoặc JVM.
- Tự động đọc giá trị hiện tại của field trong một đối tượng đang chạy.

Ví dụ, đoạn mã sau vẫn không hợp lệ nếu đặt trong một lớp không được phép truy cập `normalize()`:

```java
PrivateMemberDemo demo = new PrivateMemberDemo("Java");
demo.normalize("text"); // Lỗi truy cập: normalize() là private
```

Việc một công cụ hiển thị tên method không có nghĩa là chương trình bên ngoài được phép gọi method đó.

Reflection là cơ chế riêng để kiểm tra và tương tác với thành viên trong lúc chạy. Reflection chịu các quy tắc truy cập và giới hạn module của Java; việc biết tên private member từ `javap` không tự động cấp quyền truy cập qua reflection.

## 11. Private member, kế thừa và phạm vi class file

Private member thuộc lớp khai báo. Khi kiểm tra một lớp con, `javap -p` hiển thị các thành viên được khai báo trong class file của lớp con; nó không biến các private member của lớp cha thành thành viên của lớp con.

Ví dụ:

```java
class Base {
    private String secret;
    protected int count;
}

public class Child extends Base {
    private boolean enabled;
}
```

Khi kiểm tra:

```bash
javap -p Base
javap -p Child
```

Lệnh thứ nhất hiển thị `secret` và `count`. Lệnh thứ hai hiển thị `enabled` cùng những thành viên được khai báo trong `Child`. Muốn xem private member của lớp cha, hãy kiểm tra class file của lớp cha riêng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy private field/method | Đang dùng chế độ mặc định của javap | Thêm `-p` hoặc `-private` |
| Vẫn không thấy thành viên mong muốn | Đang kiểm tra nhầm class file hoặc nhầm classpath | Kiểm tra tên lớp, package và vị trí JAR/thư mục |
| Không hiểu descriptor | Nhầm ký hiệu JVM với kiểu Java | Dùng `-s` và đối chiếu bảng descriptor |
| Không thấy bytecode private method | Chưa thêm `-c` hoặc method không có phần thân bytecode | Dùng `-p -c`; abstract/native method không có Code thông thường |
| Không thấy giá trị hằng | Chưa dùng `-constants` hoặc field không phải constant variable phù hợp | Kiểm tra `-p -constants` và class initializer |
| Không gọi được method dù javap hiển thị | `-p` chỉ thay đổi cách hiển thị, không thay đổi quyền truy cập | Tuân thủ access control; dùng API công khai hoặc thiết kế truy cập phù hợp |
| Tên inner class không được nhận diện | Dùng sai tên nhị phân hoặc shell diễn giải ký tự `$` | Dùng tên dạng `Outer$Inner` và đặt trong dấu nháy |

## 13. Quy trình kiểm tra đề xuất

Khi cần phân tích thành viên không công khai của một lớp:

1. Xác định đúng class file hoặc JAR và tên đầy đủ của lớp.
2. Chạy `javap -p` để liệt kê tất cả field và method được khai báo.
3. Dùng `-s` để xem descriptor và phân biệt overload.
4. Dùng `-c` để đọc bytecode của method private có phần thân.
5. Dùng `-v` để kiểm tra access flags, attributes và metadata.
6. Dùng `-constants` khi cần xem giá trị hằng phù hợp.
7. Nếu là lớp kế thừa hoặc inner class, kiểm tra riêng từng class file liên quan.
8. Phân biệt kết quả phân tích class file với quyền truy cập thực tế của mã Java.

## 14. Ghi nhớ

- `javap -p` và `javap -private` hiển thị tất cả thành viên được khai báo, bao gồm private và package-private.
- Chế độ mặc định của `javap` hiển thị public và protected.
- Kết hợp `-s` để xem descriptor, `-c` để xem bytecode, `-v` để xem metadata chi tiết.
- Dùng `-constants` để xem giá trị của các hằng số phù hợp.
- Class file của lớp lồng và lớp cha cần được kiểm tra riêng khi muốn xem các thành viên được khai báo trong từng lớp.
- `javap -p` chỉ hiển thị thông tin class file; nó không thay đổi quyền truy cập private và không đọc trạng thái runtime của đối tượng.

Khi biết sử dụng `javap -p`, bạn có thể phân tích đầy đủ cấu trúc nội bộ của một lớp Java, kiểm tra API của thư viện và hiểu cách compiler biểu diễn các thành viên không công khai trong class file.
