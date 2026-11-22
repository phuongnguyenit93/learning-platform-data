# Đặt mức ngôn ngữ Java theo tính năng chính thức thực sự sử dụng

## 1. Mục tiêu: mức Java tối thiểu phải phản ánh đúng code đang phát hành

Trong một dự án Java, dòng chữ “**học Java 14**”, tên JDK đang cài trên máy, mức `source` trong IDE và phiên bản JVM triển khai **không tự động là cùng một con số**. Muốn khẳng định một artifact tương thích với Java N, phải biết code **thực sự dùng cú pháp ngôn ngữ, API nền tảng, class files và dependencies nào**, trong đó cần đặc biệt phân biệt **tính năng đã chính thức (*final/permanent*)** với tính năng **preview** ở các bản Java cũ.

Ví dụ điển hình:

- `switch expression`, nhãn `case ... ->` và `yield` trở thành tính năng ngôn ngữ **chính thức từ Java 14**.
- `text blocks` dùng dấu ba nháy kép `"""` chỉ chính thức từ **Java 15**; ở Java 14 chúng còn là preview.
- `record` và pattern matching cho `instanceof` chính thức từ **Java 16**; Java 14 chỉ có bản preview.
- `sealed class/interface` chính thức từ **Java 17**.
- Pattern matching trong `switch` và record patterns chính thức từ **Java 21**.
- `Stream.toList()` là **API thư viện xuất hiện từ Java 16**, không phải cú pháp ngôn ngữ. Một file chỉ dùng cú pháp Java 14 nhưng gọi API này vẫn **không chạy được trên Java 14** nếu API đó không tồn tại.

**Nguyên tắc trọng tâm:** chọn **mức phát hành thấp nhất đáp ứng tất cả tính năng chính thức và API mà mã nguồn thực sự sử dụng**, đồng thời kiểm tra class files và dependencies trên runtime mục tiêu. Trong pipeline dùng JDK mới để biên dịch cho Java cũ, hãy ưu tiên `javac --release N` thay vì chỉ `-source N -target N`.

Bài tập trung vào **những tính năng và công cụ hiện vẫn được hỗ trợ**. Các bản preview Java 14 chỉ được nhắc để **tránh chọn nhầm mức tương thích**; không khuyến khích mang cú pháp preview cũ làm nền tảng sản phẩm mới.

## 2. Năm loại “phiên bản Java” cần tách riêng

| Khái niệm | Ví dụ | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- | --- |
| **JDK dùng để build** | `javac 24.0.2` | Compiler, công cụ và API compile-time hiện có trên máy là gì? | Không tự chứng minh artifact chạy được trên JVM cũ |
| **Source/language level** | Java 14 | Cú pháp ngôn ngữ nào compiler chấp nhận? | Không đủ để giới hạn API dùng từ JDK mới |
| **API release level** | Java 14 | Có được phép tham chiếu `java.*`/JDK API chỉ xuất hiện sau bản 14 không? | Không kiểm soát toàn bộ hành vi của external libraries |
| **Bytecode/class-file target** | major version `58` | JVM có thể đọc định dạng class file không? | Bytecode đọc được chưa chắc các API/dependencies tồn tại |
| **Runtime tối thiểu thực tế** | JVM 14/17/21 | Artifact cùng dependencies và cấu hình có chạy được trên runtime đích không? | Phải kiểm chứng bằng chạy test trên JVM tương ứng |

Thêm một tầng rất quan trọng: **phiên bản của dependency và framework**. Bạn có thể xuất một class file theo Java 14 nhưng phụ thuộc JAR chỉ hỗ trợ Java 17; JVM 14 vẫn không thể chạy ứng dụng đầy đủ.

### 2.1. Công thức tư duy

```text
Phiên bản phát hành tối thiểu thực tế
  >= phiên bản cú pháp CHÍNH THỨC mới nhất trong source
  >=? (đánh giá độc lập) phiên bản API JDK mới nhất mà source dùng
  >=? (đánh giá độc lập) phiên bản runtime tối thiểu của dependencies
  >=? (đánh giá độc lập) yêu cầu VM/native/tooling của artifact

Quyết định cuối cùng = mức tương thích nghiêm ngặt nhất
                       trong toàn bộ chuỗi sản phẩm.
```

Hai dấu `>=?` nhắc rằng đây là **các điều kiện riêng** chứ không phải phép so sánh số học tự động. Một ứng dụng có thể không dùng cú pháp mới nhưng vẫn yêu cầu JDK 21 do API hoặc thư viện; ngược lại code dùng cú pháp Java 14 có thể chạy trên các JDK mới hơn mà không cần preview.

### 2.2. “Dùng JDK 24 để build” không đồng nghĩa “ngôn ngữ Java 24”

Compiler JDK mới có thể biên dịch cho mức cũ bằng `--release`, miễn release đó còn nằm trong danh sách được compiler hỗ trợ. Ví dụ thực tế đã xác minh:

```bash
javac --release 14 -d out14 Switch14Demo.java
```

Dù lệnh `javac` được thực thi trên **JDK 24.0.2**, compiler áp dụng **ngữ pháp, API và class-file target Java 14** cho file nguồn. Nếu mã nguồn dùng tính năng chỉ chính thức từ Java 16, bước build này thất bại, thay vì tự động “hạ cấp” tính năng.

## 3. Bảng các tính năng ngôn ngữ chính thức cần dùng để chọn mức

| Tính năng | Trạng thái tại Java 14 | **Phiên bản chính thức tối thiểu** | Có cần `--enable-preview` khi dùng ở mức chính thức? |
| --- | --- | --- | --- |
| Local variable type inference `var` | Đã chính thức | Java **10** | Không |
| Dùng `var` cho lambda parameters | Đã chính thức | Java **11** | Không |
| `switch expression`, `case ->`, `yield` | **Chính thức** | Java **14** — JEP 361 | Không |
| Text blocks `"""..."""` | **Preview lần hai** | Java **15** — JEP 378 | Không từ 15 trở đi |
| Record classes `record Point(...)` | **Preview lần đầu** | Java **16** — JEP 395 | Không từ 16 trở đi |
| Pattern matching cho `instanceof` | **Preview lần đầu** | Java **16** — JEP 394 | Không từ 16 trở đi |
| Sealed classes/interfaces | Chưa chính thức | Java **17** — JEP 409 | Không từ 17 trở đi |
| Record patterns | Chưa chính thức | Java **21** — JEP 440 | Không từ 21 trở đi |
| Pattern matching cho `switch` | Chưa chính thức | Java **21** — JEP 441 | Không từ 21 trở đi |
| Unnamed variables/patterns `_` | Chưa chính thức | Java **22** — JEP 456 | Không từ 22 trở đi |

Thông tin dựa vào bảng **Java Language Changes Summary** của Oracle Java SE 26 và các JEP của từng tính năng. Nếu Java đang dùng không có tính năng bạn cần ở dạng chính thức, có hai cách rõ ràng:

1. **Giữ baseline cũ, viết code bằng cú pháp/API có sẵn.**
2. **Nâng baseline** lên bản Java đầu tiên mà tính năng được chính thức hóa (hoặc bản cao hơn do chính sách sản phẩm).

**Không dùng “tính năng đã preview từ Java 14” như cách tuyên bố rằng code chính thức tương thích Java 14**. Một tính năng có thể được chỉnh sửa trong thời gian preview trước khi thành final; artifacts preview còn gắn với phiên bản JVM cụ thể.

### 3.1. Tính năng ngôn ngữ khác API thư viện và công cụ

| Thứ được dùng | Thuộc nhóm | Mức cần chú ý |
| --- | --- | --- |
| `case 1 -> "one"` | Cú pháp `switch` | Chính thức Java 14 |
| `record User(String name) {}` | Cú pháp khai báo class | Chính thức Java 16 |
| `"hello".strip()` | Phương thức thư viện `String` | API từ Java 11 |
| `Stream.of(1, 2).toList()` | Phương thức thư viện `Stream` | API từ Java 16 |
| `Thread.ofVirtual()` | API virtual thread builder | Java 21 |
| `jpackage` | Công cụ đóng gói | Được đưa vào JDK 14 dạng incubating; production-ready từ JDK 16 |
| `--release 14` | Option của `javac` | Giới hạn cú pháp + API JDK + bytecode |

Việc một phần **công cụ** như `jpackage` xuất hiện ở bản Java nào **không có nghĩa** source code chương trình tự động có language level bằng bản đó. Quy tắc chọn release phải áp dụng cho **mã thực tế, API và runtime sản phẩm**, không chỉ tên bài học hoặc tên JEP.

## 4. API đúng nhất để đặt mức tương thích: `javac --release N`

Khi build trên JDK hỗ trợ mục tiêu, dùng:

```bash
javac --release 14 -d out14 Switch14Demo.java
```

`--release 14` yêu cầu compiler đồng thời:

1. Dùng **quy tắc ngôn ngữ** của Java 14.
2. Tạo **class files** cho Java 14.
3. Biên dịch đối chiếu với **Java SE và JDK API được cung cấp trong Java 14** theo định nghĩa công cụ.

Ví dụ code gọi `Stream.toList()` phải bị compiler từ chối khi `--release 14`, vì phương thức ấy xuất hiện sau Java 14. **Đó là điểm quan trọng làm `--release` khác với việc chỉ đặt `-source` và `-target`.**

### 4.1. `--release` và `-source/-target` không tương đương

| Cách đặt compiler | Kiểm tra cú pháp cũ? | Đặt bytecode target? | Ràng buộc JDK APIs phiên bản cũ? | Khuyến nghị |
| --- | --- | --- | --- | --- |
| `javac --release 14` | Có | Có | **Có** | **Ưu tiên** |
| `javac -source 14 -target 14` | Có | Có | **Không tự bảo đảm**; có thể tham chiếu API JDK build mới | Tránh làm lựa chọn duy nhất |
| `javac` không option | Theo JDK đang chạy | Theo JDK đang chạy | Theo JDK đang chạy | Không đủ nếu sản phẩm đòi runtime cũ |
| IDE chọn “Language level 14” nhưng build pipeline không khóa release | Phụ thuộc IDE/build | Phụ thuộc build | Có thể khác giữa IDE và CI | Đồng bộ cấu hình tại build |

Oracle `javac` và Gradle đều khuyến nghị `--release` cho strict cross-compilation khi có thể. Không thể kết hợp `--release` cùng `-source` hoặc `-target` trong một lời gọi `javac`.

**Điều kiện áp dụng:** compiler chỉ hỗ trợ **một số phiên bản cũ nhất định**, không nhất thiết mọi release từng tồn tại. Kiểm tra:

```bash
javac -version
javac --help
```

Nếu JDK dùng để build không hỗ trợ target đã chọn, chọn toolchain JDK phù hợp; không tự thêm các flag không tương thích để ép compiler nhận một release không được hỗ trợ.

### 4.2. Những gì `--release` không bảo đảm

`--release` kiểm soát **cú pháp, bytecode và Java SE/JDK APIs** của compiler; nó **không**:

- Đảm bảo mọi dependency bên thứ ba được biên dịch cho Java 14.
- Tạo JVM 14 hoặc tự chạy test trên Java 14.
- Đảm bảo native library, JNI, OS, kiến trúc CPU và cấu hình container tương thích.
- Ngăn ứng dụng dùng reflection, dynamic class loading hoặc service provider truy cập một API chỉ có ở bản mới khi chạy.
- Đảm bảo semantic behavior của thư viện ngoài giống nhau trên mọi JDK.
- Biến feature preview cũ thành tính năng chính thức.
- Tự cấu hình test runtime, packaging runtime hoặc JDK trong production.

Vì vậy **đã biên dịch bằng `--release 14`** là điều kiện **cần**, nhưng chưa **đủ** để tuyên bố cả sản phẩm tương thích JVM 14.

## 5. Ví dụ hoàn chỉnh: `switch expression` chỉ dùng tính năng chính thức từ Java 14

Lưu thành **`Switch14Demo.java`**:

```java
public class Switch14Demo {
    static String category(int number) {
        return switch (number) {
            case 0 -> "zero";
            case 1, 2 -> {
                yield "small";
            }
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println("switch14="
                + category(0) + ","
                + category(2) + ","
                + category(9));
    }
}
```

### 5.1. Vì sao code này phù hợp Java 14?

- `switch` dùng như một **biểu thức** trả `String`.
- Nhãn `case 0 ->`, `case 1, 2 ->` và `yield` là cú pháp đã trở thành **permanent** ở Java 14.
- Các kiểu `String`, `int` và `System.out.println` không cần API mới sau Java 14.
- Không sử dụng records, text blocks, pattern matching, sealed types hoặc preview.

### 5.2. Biên dịch và chạy

```bash
javac --release 14 -d out14 Switch14Demo.java
java -cp out14 Switch14Demo
```

**Stdout đã kiểm chứng:**

```text
switch14=zero,small,other
```

Bản demo đã được biên dịch trên **OpenJDK 24.0.2** với `--release 14` và chạy trên **JVM 24.0.2**. Điều này chứng minh compiler chấp nhận **đặc tả Java 14** và class chạy được trên JDK mới; **chưa phải phép thử trực tiếp trên JVM 14**, vì môi trường kiểm thử không chạy JVM 14.

### 5.3. Kiểm tra bytecode major version

```bash
javap -verbose -classpath out14 Switch14Demo
```

Trong output của `javap` có dòng:

```text
major version: 58
```

Java 14 sử dụng class-file **major version 58**. Có thể kiểm tra nhanh bằng `javap -verbose` nhưng **class-file version phù hợp chưa bảo đảm link/runtime APIs và dependencies tương thích**. Nếu dự án bắt buộc hỗ trợ Java 14, phải chạy test suite trên Java 14 thật theo ma trận tương thích.

## 6. Text blocks: được preview ở Java 14 nhưng chính thức từ Java 15

Lưu file **`TextBlock15Demo.java`**:

```java
public class TextBlock15Demo {
    public static void main(String[] args) {
        String text = """
                hello
                world
                """;
        System.out.println("text15=" + text.replace("\n", "|"));
    }
}
```

### 6.1. Kiểm tra mức thấp hơn

```bash
javac --release 14 TextBlock15Demo.java
```

**Kết quả mong đợi và đã xác minh:** exit code khác 0, compiler JDK 24 báo:

```text
error: text blocks are not supported in -source 14
  (use -source 15 or higher to enable text blocks)
```

Đây là bằng chứng rằng **chọn mức ngôn ngữ chính thức Java 14 không được phép dùng text block syntax**. Dù Java 14 từng có text blocks dưới dạng preview, một chương trình stable Java 14 không nên dựa vào bản preview lịch sử.

### 6.2. Biên dịch ở mức chính thức đầu tiên

```bash
javac --release 15 -d out15 TextBlock15Demo.java
java -cp out15 TextBlock15Demo
```

**Stdout đã kiểm chứng:**

```text
text15=hello|world|
```

Bytecode có `major version: 59`. Mốc Java 15 là kết quả chính thức của **JEP 378**.

**Điểm cần nhớ:** nếu bài học hoặc sản phẩm dùng text blocks thì **chọn tối thiểu Java 15** cho tính năng chính thức đó, ngay cả khi các câu lệnh còn lại chỉ cần Java 14. Không chọn Java 14 rồi tự động thêm `--enable-preview` như giải pháp release mặc định.

## 7. Record classes: chính thức từ Java 16

Lưu thành **`Record16Demo.java`**:

```java
public class Record16Demo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        System.out.println("record16=" + new Point(3, 4));
    }
}
```

### 7.1. Mức 14 bị từ chối

```bash
javac --release 14 Record16Demo.java
```

JDK 24 đã báo đúng loại lỗi:

```text
error: records are not supported in -source 14
  (use -source 16 or higher to enable records)
```

### 7.2. Mức 16 thành công

```bash
javac --release 16 -d out16 Record16Demo.java
java -cp out16 Record16Demo
```

**Stdout đã kiểm chứng:**

```text
record16=Point[x=3, y=4]
```

Class file của Java 16 có **major version 60**. Record được đề xuất preview ở Java 14/15 nhưng **chính thức từ Java 16 (JEP 395)**. Việc tạo một `record` trong source mới phải được tính vào **mức ngôn ngữ tối thiểu 16**, bất kể nội dung chỉ có hai trường `int`.

### 7.3. Record còn liên quan tới API

Ngoài cú pháp `record`, Java 16 còn cung cấp reflection features để nhận diện record và contract record class. Không đánh giá khả năng tương thích chỉ dựa trên việc compiler hiểu cú pháp; code reflection, serialization libraries và version compatibility của các dependencies cũng cần được thử trên JVM mục tiêu.

## 8. Pattern matching cho `instanceof`: chính thức từ Java 16

Lưu thành **`Pattern16Demo.java`**:

```java
public class Pattern16Demo {
    public static void main(String[] args) {
        Object value = "java";
        String result = value instanceof String text
                ? "length=" + text.length()
                : "none";
        System.out.println("pattern16=" + result);
    }
}
```

Lệnh:

```bash
javac --release 14 Pattern16Demo.java
```

bị từ chối trên JDK 24 với thông điệp:

```text
error: pattern matching in instanceof is not supported in -source 14
  (use -source 16 or higher to enable pattern matching in instanceof)
```

Lệnh chính thức:

```bash
javac --release 16 -d out16 Pattern16Demo.java
java -cp out16 Pattern16Demo
```

cho output:

```text
pattern16=length=4
```

**Cẩn thận phân biệt:**

```java
if (value instanceof String) {
    String text = (String) value;
    // ...
}
```

Kiểu `instanceof` + ép kiểu truyền thống tồn tại từ trước Java 14. Cú pháp **`instanceof String text`** gắn pattern variable là tính năng khác, chỉ trở thành chính thức từ Java 16. Không gán mức ngôn ngữ dựa trên một từ khóa quen thuộc; hãy xem **cấu trúc cú pháp thực tế**.

## 9. Sealed classes: chính thức từ Java 17

Lưu file **`Sealed17Demo.java`**:

```java
sealed interface Shape permits Circle {}

record Circle(int radius) implements Shape {}

public class Sealed17Demo {
    public static void main(String[] args) {
        Shape shape = new Circle(7);
        System.out.println("sealed17="
                + shape.getClass().getSimpleName());
    }
}
```

Ví dụ kết hợp:

- `sealed interface`, `permits`: **chính thức từ Java 17**.
- `record`: chính thức từ Java 16.

Mốc tổng hợp phải là **max(17, 16) = 17**.

```bash
javac --release 17 -d out17 Sealed17Demo.java
java -cp out17 Sealed17Demo
```

**Stdout đã kiểm chứng:**

```text
sealed17=Circle
```

`javap -verbose` cho class-file **major version 61**. Với `--release 14`, compiler báo sealed classes không được hỗ trợ ở source 14. Không cố dùng chế độ preview của Java 15/16 như một cơ chế ổn định tương đương với Java 17.

## 10. Trường hợp tinh vi: cú pháp Java 14 nhưng API cần Java 16

Lưu thành **`Api16Demo.java`**:

```java
import java.util.stream.Stream;

public class Api16Demo {
    public static void main(String[] args) {
        System.out.println("api16="
                + Stream.of("A", "B").toList());
    }
}
```

Mã này không có `record`, text block, sealed class hay cú pháp mới. Tuy nhiên:

- `Stream.of(...)` xuất hiện từ Java 8.
- `Stream.toList()` là **method của API `Stream` mới có từ Java 16**.
- Do đó **mức cú pháp cũ không đủ**: runtime tối thiểu cho API này là **Java 16**.

### 10.1. Kiểm tra đúng bằng `--release 14`

```bash
javac --release 14 Api16Demo.java
```

Compiler JDK 24 từ chối với lỗi tương ứng:

```text
error: cannot find symbol
```

Nguyên nhân là `Stream.toList()` **không có trong API Java 14**, không phải vì dấu chấm hoặc cú pháp Java của method invocation không hợp lệ.

### 10.2. Biên dịch ở mức Java 16

```bash
javac --release 16 -d out16 Api16Demo.java
java -cp out16 Api16Demo
```

**Stdout đã kiểm chứng:**

```text
api16=[A, B]
```

Đây là bài học quan trọng nhất khi dự án dùng Java mới để build: **ngay cả khi không dùng một cú pháp mới, API JDK mới cũng có thể đẩy runtime tối thiểu lên**.

## 11. Cạm bẫy: `-source 14 -target 14` có thể biên dịch code không chạy được trên Java 14

Vẫn dùng `Api16Demo.java` như trên, nhưng thử:

```bash
javac -source 14 -target 14 -d out-unsafe Api16Demo.java
```

**Trên JDK 24.0.2 đã kiểm chứng: exit code = 0**, dù code gọi `Stream.toList()` chỉ có từ Java 16. Compiler cảnh báo rằng system modules location chưa được cấu hình tương thích:

```text
warning: [options] location of system modules is not set in conjunction with -source 14
  not setting the location of system modules may lead to class files that cannot run on JDK 14
    --release 14 is recommended instead of -source 14 -target 14 because it sets the location of system modules automatically
```

Xem bytecode:

```bash
javap -verbose -classpath out-unsafe Api16Demo
```

thấy:

```text
major version: 58
```

**Tại sao đây là bug nguy hiểm?** Class file mang số phiên bản **Java 14** (58) nhưng chứa lời gọi tới một method **không tồn tại trong JDK 14**. Khi chạy trên JVM 14, việc resolve lời gọi có thể dẫn đến **`NoSuchMethodError`**; class-file version một mình **không đủ** để bảo đảm runtime API compatibility.

**Không được dùng một build thành công trên JDK 24 với `-source 14 -target 14` làm bằng chứng hỗ trợ Java 14.** Cách nên dùng:

```bash
javac --release 14 Api16Demo.java
```

Nó từ chối đúng từ bước build, trước khi giao artifact cho người dùng. Đây cũng là lý do Maven và Gradle hiện hành khuyến nghị cấu hình **`release`**.

### 11.1. Một tình huống khác: dependencies có class-file major cao hơn

Giả sử application chính biên dịch thành class-file **58**, nhưng một thư viện phụ thuộc được phát hành với class-file **61** (Java 17). JVM 14 vẫn không thể nạp các class Java 17 mà application cần, có thể báo **`UnsupportedClassVersionError`**.

`--release 14` **không tự kiểm định toàn bộ dependency graph** có hỗ trợ JVM 14 hay không. Dùng dependency audit, kiểm tra bytecode của JAR và **chạy test trên JVM 14 thật** nếu runtime 14 là cam kết.

## 12. Hiểu preview đúng để không đưa mức Java sai vào sản phẩm

### 12.1. Preview không phải permanent feature

Java sử dụng cơ chế **preview** cho những ngôn ngữ/VM features có thiết kế đủ hoàn chỉnh để thử nhưng **chưa trở thành permanent**. Tính năng có thể thay đổi, lặp preview nhiều lần, được hoàn thiện hoặc bị rút lại.

Ở **Java 14**:

- `switch expressions` đã **final**: dùng trong build `--release 14` bình thường.
- `records` vẫn **preview**: chỉ **final ở Java 16**.
- `pattern matching instanceof` vẫn **preview**: chỉ **final ở Java 16**.
- `text blocks` vẫn **preview**: chỉ **final ở Java 15**.

Vì vậy lựa chọn “dùng Java 14 để chạy code record” bằng một thử nghiệm preview cũ **không tương đương** lựa chọn “dùng cú pháp record đã được chuẩn hóa từ Java 16”.

### 12.2. `--enable-preview` là ràng buộc theo đúng JDK release

Đối với một tính năng **preview của JDK phiên bản n**, biên dịch thử nghiệm bằng **compiler JDK n** với:

```text
javac --enable-preview --release n ...
java --enable-preview ...
```

Đây là **mẫu lệnh ký hiệu**, trong đó `n` phải được thay bằng **số release của JDK đang dùng**, không phải chữ `n` literal hay wildcard. Khi biên dịch preview, runtime tương ứng cũng phải bật preview và dùng release thích hợp.

Chẳng hạn: không dùng **compiler JDK 24** để mở preview lịch sử của **Java 14**. Thử nghiệm:

```bash
javac --release 14 --enable-preview Switch14Demo.java
```

**JDK 24 đã từ chối**:

```text
error: invalid source release 14 with --enable-preview
```

Không phải switch expression cần preview — thực tế nó **đã final từ 14**. Lỗi đến từ việc `--enable-preview` **không thể bật preview của một Java release lịch sử** bằng compiler khác phiên bản.

### 12.3. Class-file preview bị ràng buộc chặt với release

Theo JVM Specification, class file phụ thuộc preview thường được đánh dấu với **minor version 65535** và major version của release phát hành preview. Những class files này **không được nạp trên JDK release khác** dù JDK mới cũng có `--enable-preview`. Vì vậy preview không phải nền tảng đáng tin để tuyên bố “biên dịch một lần, chạy qua các phiên bản Java”.

**Quy trình production:** chỉ dùng các tính năng đã chính thức tại baseline cam kết; nếu đang thử nghiệm preview mới, tạo môi trường test/nhánh cấu hình tách biệt, chấp nhận tính thay đổi và không gọi đó là bản build tương thích ngược.

### 12.4. Không áp quy tắc preview cho mọi JEP

JEP có thể mô tả công cụ, thư viện, GC, API incubation hay cơ chế runtime chứ không phải cú pháp Java. Ví dụ `jpackage` xuất hiện dạng incubating ở JDK 14 nhưng thành công cụ production-ready từ JDK 16; điều này **không cho phép** suy luận rằng mọi Java source của app-image phải dùng source level 16 hoặc 14. Đánh giá riêng **source language**, **API calls** và **tool/runtime packaging**.

## 13. Dùng bytecode version để kiểm tra nhanh (nhưng không đủ)

| Java release | Class-file major version |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

Có thể kiểm tra trực tiếp:

```bash
javap -verbose -classpath out14 Switch14Demo
```

Tìm dòng `major version: 58`. Trong CI, có thể sử dụng bytecode validation plugin để kiểm tra cả artifact đầu ra và dependencies, nhưng **không thay thế test trên JVM tối thiểu**.

### 13.1. Không nhầm class-file version với API support

Các lỗi thường xuất hiện ở giai đoạn khác nhau:

| Lỗi | Nguyên nhân khả dĩ |
| --- | --- |
| `error: records are not supported in -source 14` | Code dùng cú pháp final từ Java 16 nhưng target 14 |
| `cannot find symbol: method toList()` | API `Stream.toList()` không có trong release 14 |
| `UnsupportedClassVersionError` | Class-file version mới hơn khả năng JVM nạp |
| `NoSuchMethodError` | Bytecode tham chiếu method không tồn tại trong runtime class đã nạp |
| `NoClassDefFoundError` | Class cần thiết bị thiếu/không nạp được lúc chạy |
| `ClassNotFoundException` | Tìm class theo tên không có trong classpath/module path như mong đợi |
| `UnsupportedOperationException` | Hành vi API/data structure không cho operation; **không tự chứng minh** sai Java release |

Không tự động “nâng target Java” để sửa mọi lỗi. Trước hết xác định lỗi thuộc cú pháp, API, dependency, packaging hay application logic.

## 14. Cấu hình Maven đúng: đặt `maven.compiler.release`

Trong dự án **Maven**, nên đặt trong `pom.xml`:

```xml
<project>
  <!-- Các phần cấu hình Maven project khác được đặt tại đây. -->
  <properties>
    <maven.compiler.release>14</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
</project>
```

**Đây là đoạn cấu hình minh họa, không phải `pom.xml` hoàn chỉnh để chạy một mình**: project thật phải có model/version/groupId/artifactId phù hợp. Property `maven.compiler.release` được Maven Compiler Plugin hiện hành hỗ trợ và tương ứng với compiler `--release` khi công cụ hỗ trợ.

Kiểm tra:

```bash
mvn -version
mvn clean verify
```

### 14.1. Cấu hình plugin trực tiếp

Nếu dự án khai báo `maven-compiler-plugin` riêng, có thể cấu hình:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.15.0</version>
  <configuration>
    <release>14</release>
  </configuration>
</plugin>
```

Đây là ví dụ phiên bản plugin đã được tài liệu chính thức Apache Maven mô tả; dự án cần **kiểm tra plugin/toolchain version thực tế**. Không được đặt `<release>14</release>` chỉ để tên bảng là “Java 14” nếu mã nguồn thực sự dùng tính năng final từ 16/17 hoặc API mới.

**Quan trọng:** `maven.compiler.release` kiểm soát **main/test compilation** theo cấu hình compiler plugin nhưng **không tự buộc Maven Surefire chạy unit/integration tests bằng JDK 14**. JVM chạy Maven/CI và test runtime cần được thiết kế riêng khi cam kết hỗ trợ Java 14.

### 14.2. API release không giải quyết hết external dependencies

Ngay cả khi `mvn clean verify` trên JDK 24 thành công, vẫn cần audit dependencies, transitive dependencies, runtime-activated classes và integration tests. Nếu thư viện yêu cầu JVM 17, ứng dụng không thể phát hành cho Java 14 chỉ bằng cách giảm `<release>` của compiler.

## 15. Cấu hình Gradle đúng: Java toolchain + `options.release`

Trong dự án **Gradle Kotlin DSL** (`build.gradle.kts`):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 14
}
```

Giải thích:

- `toolchain.languageVersion = JavaLanguageVersion.of(17)`: chọn **JDK 17 làm compiler/toolchain**.
- `options.release = 14`: yêu cầu JavaCompile áp dụng **ngôn ngữ/API/class-file level Java 14**.
- Toolchain và release có thể khác nhau. Chọn JDK 17 ở đây **không có nghĩa** source code phải dùng tính năng Java 17.
- Gradle phải có cấu hình tìm JDK 17 và phiên bản Gradle tương thích; toolchain download tự động chỉ hoạt động khi có cấu hình nguồn tải phù hợp.

Tham khảo `Gradle Toolchains for JVM projects`. Với **Gradle Groovy DSL** (`build.gradle`), syntax setter khác nhưng ý nghĩa `options.release` giữ nguyên.

### 15.1. Vì sao không chỉ cấu hình `sourceCompatibility/targetCompatibility`?

Hai thuộc tính đó tương đương ý tưởng `-source/-target`; chúng **không tự ngăn** tham chiếu đến APIs mới hơn từ compiler JDK mới. Gradle hiện hành khuyến nghị `options.release` cho strict cross-compilation, kết hợp toolchain nếu cần build reproducibility.

Nếu chọn minimum runtime 17, hãy dùng `options.release = 17` thay vì 14; **chọn số từ yêu cầu sản phẩm và tính năng đã thực sự dùng**.

### 15.2. IDE language level phải đồng bộ với build file

Khi IntelliJ IDEA, Eclipse hay IDE khác chỉ kiểm soát highlight/inspection, build thật còn phụ thuộc Maven/Gradle compiler. Không để:

```text
IDE language level = 14
Build release     = 17
CI compiler       = 24 default
Production JVM    = 14
```

mà không có nguyên tắc nhất quán. Nếu IDE và build tool mâu thuẫn, có thể code thấy “hợp lệ” trong IDE nhưng CI/runtime thất bại. Chọn một **source of truth** như `pom.xml`/`build.gradle.kts` và cấu hình IDE import từ build tool.

## 16. Kiểm thử tương thích theo nhiều tầng

Một pipeline đáng tin nên có ít nhất:

1. **Compilation gate**: compiler chạy `--release N`, tắt preview ở baseline stable.
2. **Dependency gate**: các JAR và transitive dependencies hỗ trợ JVM N; kiểm tra class-file versions và các APIs sử dụng.
3. **Runtime gate**: chạy unit/integration smoke tests trên **JVM thấp nhất được hỗ trợ**, không chỉ JDK build mới.
4. **Newer runtime gate**: chạy thêm trên JDK mới/lâu dài hỗ trợ để phát hiện thay đổi hành vi hoặc option bị bỏ.
5. **Packaging gate**: image/container/runtime được đóng gói có đúng JDK và modules cần thiết, không lẫn phiên bản trong CI.
6. **Release evidence**: ghi ra build metadata source release, compiler version, target runtime, dependency baseline, kết quả test.

### 16.1. Ví dụ ma trận cho dự án chủ đích hỗ trợ Java 14

| Môi trường | Mục đích | Kỳ vọng |
| --- | --- | --- |
| JDK 24 compiler với `--release 14` (nếu còn được hỗ trợ) | Chặn cú pháp/API mới | `Switch14Demo` PASS; `Record16Demo` FAIL |
| JVM 14 thật | Kiểm chứng runtime tối thiểu | Artifact và dependencies chạy trên JVM 14 nếu thật sự cam kết |
| JVM 17/21/25 (theo hệ thống hỗ trợ) | Kiểm tra compatibility phía trước | Không lỗi runtime API/logic/packaging |
| Static/dependency scan | Kiểm tra cả thư viện và binary | Không có class-file major vượt mức runtime tối thiểu |
| Các phép test reflection/JNI/OS | Những phần `--release` không kiểm soát đầy đủ | Chạy trên platform thật |

**Ghi chú triển khai:** Java 14 là bản **không thuộc nhóm LTS** và có vòng đời cập nhật lịch sử hạn chế. Nếu không có yêu cầu tương thích cũ, nên chọn một **baseline JDK hiện còn được bảo trì trong hệ thống của tổ chức**, thường là một release LTS được hỗ trợ như Java 17, 21 hoặc 25. Mục tiêu của bài là **chọn mức đúng**, không nhất thiết giữ 14 cho mọi sản phẩm mới.

### 16.2. Chạy test trên JDK mới chưa chứng minh chạy được trên JDK cũ

`javac --release 14` tạo class-file 58. Khi chạy:

```bash
java -cp out14 Switch14Demo
```

nếu `java` trong PATH là JDK 24, test này **chạy trên JDK 24**. Hãy kiểm tra `java -version` và cấu hình một **JDK 14 thật** nếu cam kết runtime 14.

**Không tuyên bố đã test trên JVM 14** chỉ vì dùng compiler option `--release 14` hoặc thấy `major version 58`. Bài demo ở đây chỉ xác nhận compile cho target Java 14 và chạy trên JDK 24 thực có.

## 17. Tổng kết bộ kiểm thử trực tiếp đã thực hiện

Trên **OpenJDK 24.0.2**, sáu file ví dụ được biên dịch bằng `javac --release ...`. Kết quả đối chiếu:

| File nguồn | `--release 14` | Release chính thức được thử thành công | Output/đặc điểm |
| --- | --- | --- | --- |
| `Switch14Demo.java` | **PASS** | **14** | `switch14=zero,small,other`, major 58 |
| `TextBlock15Demo.java` | FAIL: text blocks chưa final ở 14 | **15** | `text15=hello|world|`, major 59 |
| `Record16Demo.java` | FAIL: records chưa final ở 14 | **16** | `record16=Point[x=3, y=4]`, major 60 |
| `Pattern16Demo.java` | FAIL: pattern instanceof chưa final ở 14 | **16** | `pattern16=length=4`, major 60 |
| `Sealed17Demo.java` | FAIL: sealed chưa final ở 14 | **17** | `sealed17=Circle`, major 61 |
| `Api16Demo.java` | FAIL: API `Stream.toList` chưa tồn tại ở 14 | **16** | `api16=[A, B]`, major 60 |

Các phép thử bổ sung:

- `javac -source 14 -target 14 Api16Demo.java` trên JDK 24: **exit 0**, vẫn tạo **major version 58** dù tham chiếu API 16; compiler có cảnh báo nên dùng `--release 14`.
- `javac --release 14 --enable-preview Switch14Demo.java` trên JDK 24: **bị từ chối**, vì compiler không cho phép bật preview cho một release lịch sử.
- Mỗi chương trình được chạy bằng **JVM 24** sau khi biên dịch thành công và stdout đúng từng dòng đã ghi.

Đây là **kết quả thực nghiệm trên JDK 24**, không phải cam kết tất cả phiên bản JDK sẽ in đúng từng dấu trong error messages. Compiler version khác có thể thay nội dung thông báo, nhưng **ranh giới feature release và ý nghĩa `--release`** vẫn là các hợp đồng cần dựa vào.

## 18. Quy trình chọn baseline Java theo tính năng chính thức

### Bước 1 — Ghi chính xác các cấu trúc source đang dùng

Đọc code/build source thay vì dựa vào tên dự án, commit message hoặc Java version của IDE. Xác định có:

- `switch expression` và `yield`?
- Text blocks?
- Records, pattern matching for `instanceof`?
- Sealed classes, record patterns, pattern `switch`?
- Các feature mới hơn hoặc đang preview?

Lập bảng feature → release **đầu tiên trở thành final**. Nếu feature chỉ là preview trên baseline hiện tại, **không coi nó là final**.

### Bước 2 — Kiểm tra API JDK sử dụng

Đọc imports và method calls, đặc biệt những APIs thêm sau baseline. Ví dụ:

- `String.strip` (Java 11) không ép baseline cao hơn 14.
- `Stream.toList` (Java 16) ép baseline Java 16 nếu được gọi trực tiếp.
- `Thread.ofVirtual` (Java 21) ép baseline Java 21 nếu dùng API đó.

Dùng `javac --release N` làm **bộ lọc compiler** để phát hiện sai khác, không chỉ đọc danh sách method thủ công.

### Bước 3 — Kiểm tra dependency graph

Dự án có thể dùng một thư viện cập nhật mới chỉ hỗ trợ JDK17+. Hỏi:

- Phiên bản thư viện nào có minimum runtime Java tương ứng?
- Transitive dependencies có class-file mới hơn không?
- Framework có yêu cầu API runtime mới trong class loading hoặc reflection không?
- Native library/JNI có hỗ trợ host OS/architecture mục tiêu không?

Đừng suy ra từ việc source của chính bạn chỉ dùng `switch expression` rằng toàn bộ ứng dụng chắc chắn tương thích Java14.

### Bước 4 — Chọn release là **giá trị lớn nhất** từ các yêu cầu thật

Ví dụ:

```text
switch expression        → Java 14
text block               → Java 15
record                   → Java 16
sealed interface         → Java 17
API Thread.ofVirtual()   → Java 21
dependency runtime >= 17 → Java 17

Nếu dùng tất cả, runtime tối thiểu ít nhất = Java 21
```

Đây là bài toán chọn **mức tối thiểu đáp ứng tất cả**. Nếu công ty yêu cầu Java 17 nhưng bạn cần virtual threads, phải **đổi implementation** hoặc **nâng runtime tối thiểu**, không thể chỉ đặt `--release 17` để khiến API mới tồn tại.

### Bước 5 — Khóa phiên bản và thử thật

- Maven `<maven.compiler.release>N</maven.compiler.release>` hoặc Gradle `options.release = N`.
- Chọn compiler/toolchain hỗ trợ N.
- Build không dùng preview trong stable baseline.
- Chạy test trên JVM N thật.
- Kiểm tra bytecode và dependencies.
- Test thêm các JDK khác theo ma trận sản phẩm.

### Bước 6 — Duy trì tài liệu theo release, không theo nhãn chung

Khi code dùng thêm record hoặc API mới, cập nhật ngay tài liệu support matrix, build config và CI. Tên bài học “Java 14” chỉ cho biết **ngữ cảnh giảng dạy**, không thể thay thế bằng chứng code thực sự dùng đúng release.

## 19. Những lỗi phổ biến

### Lỗi A — Dùng `--release 14` cho code có record

**Sai về baseline chính thức:** record chỉ final ở Java 16. Compiler sẽ từ chối. Sửa bằng cách chuyển sang Java class bình thường khi cần giữ 14, hoặc nâng min runtime/source release lên 16+.

### Lỗi B — Thấy text blocks từng preview ở Java 14 nên cho rằng `--release 14` hợp lệ

Không. `--release 14` stable không hỗ trợ text blocks là tính năng permanent. Dùng 15+ hoặc cú pháp string thông thường nếu cần 14.

### Lỗi C — Mọi `switch` đều đòi Java 14

Không. `switch statement` truyền thống có từ lâu. **`switch expression` + `case ->` + `yield` theo mô hình mới là feature chính thức Java 14**.

### Lỗi D — Mọi `instanceof` đều đòi Java 16

Không. `instanceof` truyền thống tồn tại lâu; pattern variable như `instanceof String s` mới final ở Java 16.

### Lỗi E — Chỉ nhìn class-file major version

Không đủ. Major 58 có thể chứa lời gọi `Stream.toList` từ JDK mới nếu compiler dùng `-source/-target` không khóa API.

### Lỗi F — Chỉ đặt `-source/-target`

Không khóa đúng JDK platform APIs; có thể tạo class file nhìn tương thích nhưng không thực sự chạy trên JVM thấp hơn. Dùng `--release`.

### Lỗi G — Đặt `--enable-preview` rồi gọi bản build đó là permanent

Preview gắn chặt với release, có thể thay đổi và cần đúng JDK/runtime preview. Với sản phẩm cần compatibility stable, dùng feature đã final tại target.

### Lỗi H — Đặt release theo JDK build thay vì product runtime

Build trên JDK24 không buộc product phải dùng language 24; nếu cần Java17, cấu hình `--release 17`, rồi test trên JVM17.

### Lỗi I — Coi JDK14 “đã cũ” là lý do bỏ hẳn kiểm thử tương thích

Nếu ứng dụng **thực sự còn hợp đồng chạy trên Java14**, phải kiểm tra bằng Java14; đồng thời ghi nhận rủi ro bảo trì/bảo mật và có lộ trình nâng lên JDK được hỗ trợ. Ngược lại, không tự áp Java14 làm minimum cho dự án mới chỉ vì khóa học có tên Java14.

### Lỗi J — Bỏ qua runtime dependencies

Main class version58 chưa đủ khi một transitive JAR dùng major61 hoặc API chỉ có Java17. Test đúng dependency graph và runtime.

### Lỗi K — IDE hiển thị đúng nhưng CI build khác

IDE source level và build tool compiler release phải đồng bộ. CI nên đọc cấu hình từ Maven/Gradle và in ra compiler/runtime versions để truy lỗi.

### Lỗi L — Không phân biệt API JVM với tool phát hành

`jpackage` là công cụ xây package, không phải cú pháp Java main. Một app dùng Java14 switch có thể được đóng gói bởi JDK mới, nhưng **runtime bundle** phải đủ tương thích với API/bytecode của app và chính policy triển khai.

### Lỗi M — Tin rằng compile trên JDK mới với `--release 14` đã kiểm thử JVM14

Chưa. Compiler check mạnh nhưng không thay runtime test. Chạy test suite bằng **JDK14 thật** nếu phải hỗ trợ nó, đồng thời kiểm tra dependencies và native integration.

## 20. Bài tập tự đánh giá

**Câu 1.** Một class chỉ dùng `switch expression`/`yield`, không gọi API mới. Chọn mức ngôn ngữ chính thức tối thiểu?

**Đáp án:** Java **14**.

**Câu 2.** Thêm text block vào class ở câu 1. Mức mới?

**Đáp án:** Java **15**. Text blocks preview ở 14 nhưng permanent ở 15.

**Câu 3.** Thêm `record Point(int x, int y)`. Mức mới?

**Đáp án:** Java **16**. Records chỉ permanent từ Java16.

**Câu 4.** Có `if (obj instanceof String s)` thì tối thiểu bao nhiêu?

**Đáp án:** Java **16** cho pattern matching instanceof; `instanceof String` không pattern không có yêu cầu đó.

**Câu 5.** Dự án có record và sealed interface. Mức tối thiểu?

**Đáp án:** Java **17**. Lấy mức lớn nhất giữa các tính năng cần.

**Câu 6.** Chương trình không dùng cú pháp mới nhưng gọi `Stream.toList()`. `--release 14` sẽ như thế nào?

**Đáp án:** Bị từ chối vì API không tồn tại ở Java14. Muốn dùng trực tiếp method này cần Java16+ hoặc thay bằng một API sẵn có ở baseline.

**Câu 7.** Vì sao `javac -source 14 -target 14` có thể gây lỗi runtime?

**Đáp án:** Hai option chỉ điều khiển syntax và class-file target; không tự chặn APIs chỉ có ở JDK compiler mới. Artifact có thể link tới method vắng mặt ở runtime cũ.

**Câu 8.** Class có `major version 58`. Có được tuyên bố toàn bộ app chạy trên JVM14 không?

**Đáp án:** Không. Cần kiểm tra các class phụ thuộc, platform APIs và chạy trên JVM14 thật.

**Câu 9.** Tại sao không dùng `--enable-preview --release 14` với compiler JDK24?

**Đáp án:** Preview chỉ được bật cho release tương ứng với compiler đang chạy. JDK24 không dùng để bật preview lịch sử Java14; compiler từ chối.

**Câu 10.** Maven và Gradle nên khóa ở đâu?

**Đáp án:** Maven dùng `maven.compiler.release` hoặc cấu hình compiler plugin `release`. Gradle dùng `options.release`, thường kết hợp Java toolchain.

**Câu 11.** Compile bằng `--release 14` trên JDK24 và chạy trên JDK24 thành công. Còn thiếu kiểm chứng gì nếu phải hỗ trợ Java14?

**Đáp án:** Chạy unit/integration smoke tests trên **JVM14 thật**, kiểm tra dependencies và hành vi native/OS.

**Câu 12.** Nếu product yêu cầu JVM17 nhưng code gọi `Thread.ofVirtual()` thì sao?

**Đáp án:** Đây là API Java21; hoặc nâng min runtime lên Java21, hoặc sửa code dùng API hợp lệ ở Java17. Không giải quyết bằng `-source 17 -target 17`.

## 21. Checklist cho bài kiểm thử tương thích

- [ ] Biết chính xác runtime JDK thấp nhất **sản phẩm** phải hỗ trợ.
- [ ] Phân biệt JDK build, language level, platform API release, class-file target và runtime JVM.
- [ ] Liệt kê cú pháp hiện dùng theo **phiên bản trở thành permanent**, không theo bản preview đầu tiên.
- [ ] Java14: `switch expression/yield` permanent; records/pattern instanceof/text blocks ở đó vẫn preview.
- [ ] Với text blocks chọn tối thiểu Java15, records và instanceof patterns Java16, sealed Java17.
- [ ] Quét cả **JDK API method calls**, ví dụ `Stream.toList` cần Java16.
- [ ] Dùng `javac --release N` hoặc tương đương Maven/Gradle; không chỉ `-source/-target`.
- [ ] Không bật `--enable-preview` khi xây baseline stable không dùng preview.
- [ ] Kiểm tra compiler có hỗ trợ target N bằng `javac --help`; không giả định mọi JDK giữ tất cả historical targets.
- [ ] Dùng `javap -verbose`/bytecode tool kiểm tra class-file major, nhưng không xem đó là phép chứng minh cuối cùng.
- [ ] Kiểm tra transitive dependencies, plugin/framework runtime requirements.
- [ ] Chạy test trên JVM tối thiểu thực tế; một JDK build mới không thay test này.
- [ ] Test thêm trên JDK mới được hỗ trợ trong sản phẩm, và trên đúng OS/container.
- [ ] Đồng bộ IDE và CI với Maven/Gradle toolchains/build config.
- [ ] Ghi lại compiler/runtime versions, source release và bằng chứng test trong phát hành.
- [ ] Đối với dự án mới, ưu tiên một phiên bản JDK còn được nhà cung cấp/tổ chức hỗ trợ thay vì mặc định giữ release non-LTS cũ.
- [ ] Mỗi khi đưa thêm tính năng/API, cập nhật release baseline, CI matrix và tài liệu hỗ trợ.

## 22. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html): bảng tính năng permanent/preview từ Java9 đến Java26, bao gồm switch14, text blocks15, record/instanceof16, sealed17, pattern switch21.
2. [Oracle Java SE 25 — `javac` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): định nghĩa chính xác `--release`, `-source`, `-target`, platform API compatibility, hạn chế cross-compilation.
3. [Oracle Java SE 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): tính chất chưa permanent, flags biên dịch/runtime và ràng buộc theo JDK release.
4. [OpenJDK — JEP 361: Switch Expressions](https://openjdk.org/jeps/361): feature permanent Java14.
5. [OpenJDK — JEP 378: Text Blocks](https://openjdk.org/jeps/378): feature permanent Java15.
6. [OpenJDK — JEP 395: Records](https://openjdk.org/jeps/395): feature permanent Java16.
7. [OpenJDK — JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394): feature permanent Java16.
8. [OpenJDK — JEP 409: Sealed Classes](https://openjdk.org/jeps/409): feature permanent Java17.
9. [Apache Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình `maven.compiler.release` và các giới hạn.
10. [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): kết hợp toolchain với `options.release`, cảnh báo `sourceCompatibility/targetCompatibility`.
11. [The Java Virtual Machine Specification — Class-file Versions](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-4.html): `major_version`, `minor_version` và quy tắc bytecode/preview.
