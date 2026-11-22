# Kiểm tra bytecode sau compilation

## 1. Mục tiêu: nhìn thấy compiler đã tạo gì từ pattern matching

Khi lập trình Java 21, mã nguồn có thể sử dụng `instanceof` type pattern, record pattern, `switch` với `when`, sealed interface và các biến pattern có phạm vi phụ thuộc luồng điều khiển. Sau khi `javac` biên dịch, JVM **không chạy trực tiếp cú pháp Java nguồn** mà thực thi các chỉ thị trong **class file**. Vì vậy, kiểm tra bytecode là kỹ năng hữu ích khi:

- Muốn hiểu cách compiler biểu diễn một phép kiểm tra kiểu hoặc phân rã record.
- Muốn xác minh module thực sự được biên dịch với mức Java 21, thay vì chỉ chạy trên một JVM 21.
- Muốn xem cấu trúc record, các subtype được `permits`, các phương thức tổng hợp hoặc bootstrap liên quan `switch`.
- Muốn phân biệt thao tác thực sự có mặt trong bytecode với suy đoán như “pattern không gọi accessor”.
- Muốn điều tra lỗi runtime do **không tương thích phiên bản class file**, thiếu dependency hoặc quá trình build dùng nhầm compiler.

Công cụ chính là **`javac`** (biên dịch) và **`javap`** (hiển thị cấu trúc và chỉ thị bytecode của class file). Chúng có sẵn cùng JDK; không cần tải một decompiler bên thứ ba để thực hiện các bước cơ bản.

**Giới hạn quan trọng:** `javap` cho thấy bytecode đã biên dịch, **không phải mã máy sau tối ưu JIT** và không phải bằng chứng trực tiếp rằng một biểu thức nhanh/chậm hơn biểu thức khác. Một lời gọi có mặt trong bytecode có thể được JIT inline khi chạy; một nhánh có thể được tối ưu theo thông tin runtime. Muốn kết luận về hiệu năng cần profiler hoặc benchmark đúng cách.

## 2. Chuẩn bị đúng toolchain

Bài sử dụng những tính năng **chính thức từ Java 21**:

- Type pattern trong `instanceof` đã chính thức từ Java 16.
- Record và sealed interface lần lượt đã chính thức từ Java 16 và Java 17.
- **Record patterns** và **pattern matching for `switch`** chính thức trong Java 21 (JEP 440, JEP 441).

Kiểm tra các công cụ trên terminal:

```bash
java -version
javac -version
javap -version
```

Các lệnh cần sử dụng **một bộ công cụ JDK phù hợp**. Nếu `java` và `javac` trỏ tới các bản cài đặt khác nhau, chương trình có thể biên dịch thành class file mà runtime hiện tại không hỗ trợ.

Với JDK 21, mức class file tương ứng là **major version 65**. Mức Java 17 là **major 61**. Có thể kiểm tra phiên bản class file bằng `javap -verbose` thay vì suy đoán từ tên thư mục hoặc phiên bản IDE.

Khi muốn đảm bảo API và ngôn ngữ Java 21, biên dịch với:

```bash
javac --release 21 -encoding UTF-8 -g PatternBytecodeInspectionDemo.java
```

Các tùy chọn:

- `--release 21`: yêu cầu compiler hỗ trợ mức nguồn, class file và API nền tảng của Java 21. Nó **không biến một `javac` cũ thành compiler Java 21**.
- `-encoding UTF-8`: đọc tệp nguồn có tiếng Việt một cách nhất quán.
- `-g`: yêu cầu thêm thông tin debug (như dòng nguồn và biến cục bộ), giúp việc đối chiếu kết quả `javap` dễ hơn.

Không cần `--enable-preview` cho các pattern chính thức dùng trong bài. Đừng bật preview như một cách chữa mọi lỗi compile, vì nó có chính sách phiên bản riêng và có thể tạo class file không chạy được trên các môi trường khác.

## 3. Chương trình mẫu Java 21 hoàn chỉnh

Tạo tệp tên chính xác **`PatternBytecodeInspectionDemo.java`**:

```java
public class PatternBytecodeInspectionDemo {
    record Point(int x, int y) {}

    record Box(String label, Point point) {}

    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    record Rectangle(int width, int height) implements Shape {}

    // Record pattern: phân rã component.
    static int sumWithPattern(Object value) {
        if (value instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    // Type pattern: chỉ ràng buộc object,
    // rồi gọi accessor trong thân if.
    static int sumWithTypePattern(Object value) {
        if (value instanceof Point point) {
            return point.x() + point.y();
        }
        return -1;
    }

    // Nested record pattern.
    static String boxLabel(Object value) {
        if (value instanceof Box(
                String label, Point(int x, int y))) {
            return label + ":" + (x + y);
        }
        return "no match";
    }

    // Pattern switch, guard when và sealed hierarchy.
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle(int radius) when radius >= 10 ->
                    "large circle:" + radius;

            case Circle(int radius) ->
                    "circle:" + radius;

            case Rectangle(int width, int height) ->
                    "rectangle:" + (width * height);

            case null ->
                    "null shape";
        };
    }

    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(sumWithPattern(point));
        System.out.println(sumWithTypePattern(point));
        System.out.println(sumWithPattern("other"));

        System.out.println(boxLabel(
                new Box("B", new Point(1, 2))));
        System.out.println(boxLabel(new Box("B", null)));

        System.out.println(describe(new Circle(12)));
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Rectangle(2, 4)));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 -g PatternBytecodeInspectionDemo.java
java PatternBytecodeInspectionDemo
```

**Standard output mong đợi:**

```text
5
5
-1
B:3
no match
large circle:12
circle:3
rectangle:8
null shape
```

Giải thích từng nhóm kết quả:

1. Hai hàm tính tổng đều nhận `Point(2,3)` và trả `5`. Một hàm dùng record pattern, một hàm dùng type pattern và gọi accessor rõ ràng.
2. Chuỗi `"other"` không phải `Point` nên `sumWithPattern` trả `-1`.
3. `Box("B", Point(1,2))` khớp nested pattern, trả `B:3`; `Box("B", null)` không khớp mẫu con `Point(...)`, trả `no match`.
4. `Circle(12)` khớp guard `radius >= 10` và tạo `large circle:12`. `Circle(3)` trượt guard rồi khớp case `Circle` không guard, tạo `circle:3`.
5. `Rectangle(2,4)` cho `rectangle:8`. Selector `null` được xử lý riêng bởi `case null`.

Chương trình này giữ dữ liệu nhỏ và kết quả xác định, để người đọc có thể **kiểm tra hành vi source trước khi phân tích bytecode**. Không so sánh hiệu năng bằng số dòng bytecode được in ra.

## 4. Bước một: quan sát các tệp .class được sinh ra

Sau lệnh `javac`, class chính và các kiểu lồng thường xuất hiện dưới những tên như:

```text
PatternBytecodeInspectionDemo.class
PatternBytecodeInspectionDemo$Point.class
PatternBytecodeInspectionDemo$Box.class
PatternBytecodeInspectionDemo$Shape.class
PatternBytecodeInspectionDemo$Circle.class
PatternBytecodeInspectionDemo$Rectangle.class
```

Dấu `$` ở tên nhị phân biểu diễn các kiểu member lồng, không phải ký hiệu pattern đặc biệt. Không chỉnh sửa bằng tay class file hay đổi tên những tệp đó. Thực tế số lượng và tên class file còn phụ thuộc những class được khai báo trong chương trình.

Trên PowerShell có thể liệt kê:

```powershell
Get-ChildItem -Filter 'PatternBytecodeInspectionDemo*.class'
```

Trên shell POSIX:

```bash
ls PatternBytecodeInspectionDemo*.class
```

Nếu biên dịch trong dự án Maven/Gradle, class file thường nằm trong thư mục output build (ví dụ `target/classes` hoặc `build/classes/java/main`), không nhất thiết ở thư mục hiện tại. Khi đó, hãy dùng `-classpath` của `javap` trỏ tới output đang kiểm tra; tránh nhìn nhầm class file của một lần build cũ.

## 5. Các tùy chọn javap nên nhớ

| Tùy chọn | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `javap ClassName` | Danh sách chữ ký thành viên có thể truy cập theo chế độ hiển thị mặc định | Kiểm tra sơ bộ cấu trúc lớp. |
| `-p` / `-private` | Hiển thị cả các thành viên private | Xem các phương thức và cấu trúc do compiler sinh. |
| `-c` | Disassemble phần mã của phương thức thành JVM instructions | Đối chiếu `instanceof`, `checkcast`, invocation, branch, switch. |
| `-l` | Hiển thị thông tin dòng nguồn và biến cục bộ nếu class file chứa chúng | Theo dõi biến pattern và dòng nguồn; kết hợp `javac -g`. |
| `-s` | Hiển thị JVM type descriptors của trường/phương thức | Đối chiếu chữ ký cấp JVM, ví dụ kiểu `I` và `Ljava/lang/String;`. |
| `-v` / `-verbose` | Thông tin chi tiết: class version, constant pool, attributes, bootstrap methods và mã | Điều tra class file version, `Record`, `PermittedSubclasses`, `BootstrapMethods`. |
| `-classpath <path>` | Chọn đường dẫn tra class cần hiển thị | Tránh đọc nhầm file hoặc build output. |

Lệnh thường dùng nhất để đọc phương thức:

```bash
javap -c -p -l PatternBytecodeInspectionDemo
```

Nếu cần xem version, constant pool và bootstrap:

```bash
javap -v -p PatternBytecodeInspectionDemo
```

Bản verbose có thể rất dài. Hãy ưu tiên xem đúng class, phương thức và attribute liên quan trước, thay vì kết luận từ một đoạn output bị cắt mất phần đầu/cuối.

**Tên kiểu lồng phải được quote đúng khi chạy shell.** Trong PowerShell và nhiều shell POSIX, dùng dấu nháy đơn để tránh dấu `$` bị xử lý như tên biến:

```bash
javap -p -c 'PatternBytecodeInspectionDemo$Point'
javap -v -p 'PatternBytecodeInspectionDemo$Shape'
javap -v -p 'PatternBytecodeInspectionDemo$Box'
```

Nếu truyền `PatternBytecodeInspectionDemo$Point` không quote trong một shell có nội suy dấu `$`, tên có thể bị thay đổi khiến `javap` báo không tìm thấy class hoặc mở một class không như dự định.

## 6. Bước hai: kiểm tra bytecode của instanceof và type pattern

Với:

```java
if (value instanceof Point point) {
    return point.x() + point.y();
}
```

Compiler phải triển khai ngữ nghĩa sau: xác nhận giá trị có kiểu thích hợp, lấy tham chiếu có kiểu tương ứng và thực hiện hai lời gọi accessor. Trong bytecode được tạo bởi `javac`, những chỉ thị hoặc nhóm chỉ thị có thể gặp gồm:

- **`instanceof`**: kiểm tra kiểu runtime và tạo kết quả boolean tương ứng.
- **`checkcast`**: kiểm tra/đưa tham chiếu về kiểu cần dùng ở những vị trí compiler chọn.
- **`invokevirtual`**: thường là lời gọi accessor của record class, ví dụ `Point.x()`, `Point.y()`.
- **`iadd`**: phép cộng hai số nguyên.
- **`ifeq`, `ifne`, `goto`**: nhánh điều khiển tương ứng với kết quả kiểm tra.
- **`ireturn`**: trả một giá trị kiểu `int`.

Đây là **các dấu hiệu để tìm**, không phải cam kết chuỗi chỉ thị chính xác hoặc thứ tự cố định. Compiler được phép chọn cách hạ cú pháp (*lowering*) khác nhau miễn tuân thủ đặc tả ngôn ngữ và JVM.

Để xem:

```bash
javap -c -p PatternBytecodeInspectionDemo
```

Tìm phương thức `sumWithTypePattern`, đối chiếu `instanceof` với nhánh thất bại trả `-1`, rồi kiểm tra các lời gọi accessor. Với `sumWithPattern`, record pattern phải **đảm bảo ngữ nghĩa phân rã** bằng accessor theo đặc tả, nhưng implementation bytecode có thể dùng biến cục bộ hoặc cấu trúc điều khiển khác phiên bản thủ công.

Đừng đoán kiểu nguồn của biến chỉ từ một chỉ thị `aload`: trong JVM, `aload` đưa tham chiếu từ local slot lên operand stack; kiểu tĩnh có thể cần xem descriptor, stack-map frame và các bước cast/type-check liên quan.

## 7. Bước ba: record pattern và các lời gọi accessor

Mẫu:

```java
if (value instanceof Point(int x, int y)) {
    return x + y;
}
```

khác với một phép thử kiểu trần `instanceof Point`. Khi record pattern khớp, việc phân rã component theo Java 21 sử dụng các **accessor** `x()`, `y()`; sau đó component pattern được kiểm tra và biến `x`, `y` được ràng buộc.

Hãy so sánh hai phương thức:

```bash
javap -c -p -l PatternBytecodeInspectionDemo
```

Một quy trình đọc đúng:

1. Xác định ranh giới của `sumWithPattern` và `sumWithTypePattern` trong bản disassembly.
2. Tìm các kiểm tra subtype, lệnh gọi accessor và các nhánh thất bại.
3. Với `javac -g`, dùng `LineNumberTable` và `LocalVariableTable` để hỗ trợ đối chiếu tên biến và dòng nguồn.
4. Không khẳng định “record pattern không gọi getter” chỉ vì mã Java không có từ `.x()`.
5. Không khẳng định hai phiên bản có chi phí runtime giống hoặc khác chỉ vì số dòng bytecode gần nhau.

### Accessor của record do compiler tạo

Kiểm tra class của record:

```bash
javap -p -c 'PatternBytecodeInspectionDemo$Point'
javap -v -p 'PatternBytecodeInspectionDemo$Point'
```

Bạn có thể quan sát:

- Các field gắn với component và phương thức `x()`/`y()`.
- Constructor nhận các component.
- Những phương thức của record như `equals`, `hashCode`, `toString`; compiler thường dùng cơ chế `invokedynamic` và `java.lang.runtime.ObjectMethods` để hỗ trợ các phương thức sinh tự động này.
- **`Record` attribute** mô tả các component trong class file.

**Lưu ý:** record có thể tự khai báo accessor với logic tùy chỉnh. Gọi accessor không đồng nghĩa “đọc field luôn rẻ”; nó có thể tính toán, có tác dụng phụ hoặc ném exception. Nếu một accessor ném exception trong quá trình matching record pattern, Java 21 quy định trường hợp đó được biểu diễn qua `MatchException` với nguyên nhân gốc. Lời gọi accessor trực tiếp ngoài pattern có thể bộc lộ loại exception khác. Khi điều tra hành vi lỗi, nên xem cả source, class file và test chứ không chỉ đếm opcode.

### Nested pattern có thể phải đi qua nhiều cấp

Mẫu:

```java
if (value instanceof Box(
        String label, Point(int x, int y))) {
    return label + ":" + (x + y);
}
```

yêu cầu truy cập component `label` và `point` của `Box`, rồi phân rã tiếp `x`, `y` của `Point` nếu mẫu lồng khớp. Khi `point == null`, nested `Point(...)` không khớp. Điều đó khác với việc chỉ kiểm tra `value instanceof Box box` rồi truy cập một field tùy ý.

Trong bản bytecode, hãy tìm các lời gọi tới accessor của `Box` và `Point`, các bước kiểm tra kiểu/thành phần, và các nhánh đi đến `"no match"`. Không nên giả định mọi accessor đều được gọi với mọi input: khi một bước khớp thất bại, các bước sau có thể bị bỏ qua theo ngữ nghĩa pattern.

## 8. Bước bốn: giải mã switch pattern và guard when

Phương thức:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius >= 10 ->
                "large circle:" + radius;
        case Circle(int radius) ->
                "circle:" + radius;
        case Rectangle(int width, int height) ->
                "rectangle:" + (width * height);
        case null -> "null shape";
    };
}
```

có hai bước logic cần nhận ra trong bytecode: **chọn kiểu/pattern phù hợp** và **đánh giá guard**. Guard chỉ có ý nghĩa sau khi mẫu `Circle` khớp; nếu `radius < 10`, nhánh `Circle` phía sau có thể được chọn.

Với `javac` Java 21, khi disassemble pattern-matching `switch`, có thể gặp:

- **`invokedynamic`** dùng cơ chế bootstrap của JVM, trong đó **`java.lang.runtime.SwitchBootstraps.typeSwitch`** là tên cần nhận diện khi xem `BootstrapMethods`.
- Những nhánh như **`tableswitch`** hoặc **`lookupswitch`** để điều hướng tới các case được biên dịch.
- Kiểm tra component của record và so sánh guard bằng các chỉ thị thao tác số nguyên/nhánh điều kiện.
- Các nhánh fallback hoặc mã bảo vệ để duy trì tính an toàn khi cấu trúc kiểu runtime không còn giống giả định khi compile.

Lệnh:

```bash
javap -v -p PatternBytecodeInspectionDemo
```

cho phép quan sát **constant pool**, các mục `InvokeDynamic`, `BootstrapMethods` và cách chúng liên hệ với phương thức `describe`. Kết hợp với:

```bash
javap -c -p PatternBytecodeInspectionDemo
```

để theo dõi luồng điều khiển ở cấp JVM.

**Không mặc định `switch` luôn sinh ra đúng một `tableswitch`** hoặc luôn có một thứ tự opcode giống nhau. Cách biên dịch phụ thuộc dạng selector/case, thuật toán của `javac` và phiên bản compiler. Mục tiêu là nhận diện ngữ nghĩa, không học thuộc một listing cố định rồi coi đó là chuẩn Java.

### Guard false không phải exception

Nếu `Circle(3)` khớp record pattern nhưng `radius >= 10` sai, `switch` thử case tiếp theo. Nếu accessor hoặc guard **ném exception**, ngữ nghĩa khác: nó không tự chuyển exception thành `false` rồi đi tiếp. Bytecode có thể có exception handler phục vụ ngữ nghĩa pattern; muốn xác nhận hãy xem `Exception table` và phần mã liên quan trong `javap -v`, đồng thời dùng test đầu vào gây lỗi có kiểm soát.

## 9. Bước năm: kiểm tra sealed hierarchy và record metadata

Với:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

lệnh:

```bash
javap -v -p 'PatternBytecodeInspectionDemo$Shape'
```

có thể hiển thị **`PermittedSubclasses` attribute**, liệt kê các subtype trực tiếp được cho phép theo class file. Đây là bằng chứng về ranh giới hierarchy ở cấp binary, không phải bản liệt kê mọi đối tượng runtime đang tồn tại.

Đối với record:

```bash
javap -v -p 'PatternBytecodeInspectionDemo$Circle'
```

tìm:

- Class kế thừa `java.lang.Record`.
- Attribute **`Record`** mô tả component `radius`.
- Chữ ký constructor, accessor `radius()` và các phương thức record được sinh tự động.
- `NestHost`/`InnerClasses` hoặc thông tin liên quan đến kiểu lồng, tùy cấu trúc class file.

Điều cần phân biệt: `PermittedSubclasses` thuộc kiểu `sealed`, còn `Record` attribute mô tả **cấu trúc component**. Chúng không thay thế nhau và không tự chứng minh mọi giá trị component hợp lệ về nghiệp vụ.

## 10. Phiên bản class file, debug info và tương thích runtime

Dùng:

```bash
javap -v PatternBytecodeInspectionDemo
```

Tìm các thông tin như:

```text
major version: 65
```

Với chương trình được biên dịch bằng `--release 21`, đây là kết quả mong đợi. Các vùng như `flags`, `this_class`, `super_class`, `Constant pool`, `SourceFile` và `BootstrapMethods` giúp hiểu class file đã tạo.

**Những điều không nên suy luận sai:**

- Runtime `java -version` là Java 21 **không bảo đảm** toàn bộ class đang được chạy đã được compile ở Java 21; chúng có thể được build bằng `--release 17`.
- `major version: 65` xác nhận định dạng class file tương ứng Java 21, **không xác nhận** mọi branch/guard đều đúng nghiệp vụ.
- Class file build cho Java 21 thường **không chạy trên JVM Java 17**; khi tải class không hỗ trợ, có thể gặp `UnsupportedClassVersionError`.
- `LineNumberTable` không phải một phép ánh xạ một-một từ mỗi câu lệnh Java sang opcode. Compiler có thể tạo nhiều chỉ thị từ một biểu thức hoặc gộp nhiều thao tác nguồn.
- Các biến pattern thường được biểu diễn bằng local slots/stack và nhánh; tên biến nguồn chỉ xuất hiện trong debug metadata nếu có, không phải “biến JVM” độc lập với vùng lưu trữ.
- Dùng `javap -c` không cho biết thời gian chạy, số lần JIT inline hay mã máy cuối cùng.

### Khi cần kiểm tra biến pattern và phạm vi

Biên dịch bằng `-g` như ở phần 2 rồi chạy:

```bash
javap -c -l -p PatternBytecodeInspectionDemo
```

Tìm `LocalVariableTable`, nếu có, để xem **local slot**, thời điểm bắt đầu và độ dài vùng bytecode mà tên biến được ghi trong thông tin debug. Điều đó hỗ trợ tra cứu, nhưng **flow scoping theo đặc tả Java** vẫn là quy tắc ở cấp nguồn; debug range không phải định nghĩa chính thức của scope ngôn ngữ.

Nếu biên dịch không có `-g`, có thể thiếu metadata của tên biến cục bộ. Vì vậy, việc không thấy tên `radius` hoặc `point` trong `javap` **không có nghĩa compiler không sử dụng local variable**.

## 11. Áp dụng trong Maven, Gradle và CI

### Maven

Trong dự án Maven có cấu hình `maven-compiler-plugin` phù hợp và JDK hỗ trợ Java 21, có thể khai báo mức biên dịch:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Cách cấu hình cụ thể còn phụ thuộc phiên bản plugin và toolchain của dự án. Sau khi build, có thể kiểm tra class file đã sinh:

```bash
javap -classpath target/classes -v com.example.PatternBytecodeInspectionDemo
```

Lệnh trên giả định dự án đặt class trong package `com.example`. Nếu class nằm trong package khác, dùng **tên fully qualified thực tế**; đừng sử dụng nguyên đường dẫn ví dụ như một class tồn tại sẵn.

### Gradle

Ví dụ Gradle **Groovy DSL** để chọn toolchain Java 21:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Đây là snippet cấu hình, không phải `build.gradle` đầy đủ; dự án phải áp dụng Java plugin thích hợp và phiên bản Gradle hỗ trợ JDK/toolchain đang dùng. Sau build, kiểm tra output tương ứng:

```bash
javap -classpath build/classes/java/main -v com.example.PatternBytecodeInspectionDemo
```

Với cả Maven và Gradle, hãy **xác nhận thật sự dùng đúng build output**, thay vì trỏ tới tệp `.class` ở một vị trí cũ. CI cũng nên cố định hoặc ghi nhận phiên bản `java`/`javac`, cấu hình `--release` và các plugin tạo bytecode sau biên dịch như bytecode enhancement/instrumentation nếu có.

### Một quy trình CI thực tế

1. Build với JDK và `--release` đã chốt.
2. Chạy unit test để xác minh **ngữ nghĩa** pattern và guard.
3. Khi có nhu cầu tương thích, kiểm tra class file version và các attribute quan trọng.
4. Khi điều tra lỗi chuyên sâu, lưu disassembly tương ứng **artifact đang phát hành**, không dùng kết quả từ workspace khác.
5. Không biến một listing bytecode cụ thể thành golden test quá cứng nếu compiler/JDK được phép cập nhật; kiểm tra **bất biến có ý nghĩa** như version, metadata và hành vi.

## 12. So sánh bytecode không đủ để kết luận hiệu năng

Một câu hỏi hay gặp: “Hai cách viết `Point(int x, int y)` và `Point point` rồi gọi `point.x()`/`point.y()` có cách nào nhanh hơn?”

`javap` giúp thấy **các lời gọi/nhánh có trong class file**. Nhưng:

- JVM có thể inline accessor rất nhỏ, loại bỏ một số thao tác dư thừa khi có đủ thông tin.
- Record pattern với guard nhiều case có thể gọi accessor lặp lại ở những đường đi khác nhau; tần suất thực tế phụ thuộc dữ liệu.
- Số opcode không đại diện trực tiếp số chu kỳ CPU; cache, JIT, loại đối tượng runtime, allocation và branch prediction đều có thể quan trọng.
- Microbenchmark thiếu warm-up, có dead-code elimination hoặc đo một input duy nhất rất dễ gây kết luận sai.

Muốn kiểm tra hiệu năng, dùng **JMH** hoặc profiler phù hợp, thống nhất workload, dữ liệu, JDK, warm-up, số lượt đo và đường đi true/false của guard. Dùng `javap` để **đặt giả thuyết và giải thích** kết quả benchmark, không dùng bytecode làm thay benchmark.

Nếu một accessor tùy chỉnh có tác dụng phụ, hãy xem đó là vấn đề **đúng đắn và khả năng bảo trì** trước khi tối ưu: record pattern có thể gọi accessor để phân rã, vì vậy đổi mã nguồn mà không xét hành vi accessor có thể làm thay đổi kết quả hoặc exception được quan sát.

## 13. Các lỗi thường gặp khi đọc javap

| Hiện tượng | Cách hiểu sai | Cách xử lý |
| --- | --- | --- |
| Không thấy `radius` trong output `javap -c` | “Compiler không tạo biến pattern” | Compile `-g` và xem `-l`/`LocalVariableTable`; phân biệt metadata với bytecode thực thi. |
| Thấy `invokedynamic` | “Chắc chắn chương trình chậm vì dynamic” | Kiểm tra bootstrap liên quan (`typeSwitch`, `ObjectMethods`, `StringConcatFactory`...) và đo runtime nếu cần. |
| Không thấy `tableswitch` đúng như tài liệu minh họa | “Compiler đã bỏ qua switch” | Tìm cấu trúc dispatch thực tế; compiler được phép hạ cú pháp bằng nhiều cách. |
| Thấy lời gọi accessor | “Record pattern luôn chậm” | JIT có thể inline; xem workload và profiler. |
| `ClassNotFound` khi `javap` kiểu lồng | “Không có class file của record” | Quote tên có `$`, kiểm tra classpath và output directory. |
| Thấy major version 65 | “Code này chắc chắn chạy ở mọi Java” | Runtime phải hỗ trợ class file Java 21 và đầy đủ dependency. |
| Thiếu `PermittedSubclasses` trên một class thường | “javac build sai” | Attribute dành cho kiểu `sealed`; kiểm tra đúng class/interface gốc. |
| Không thấy nhánh null như một case rõ trong bytecode | “Source không xử lý null” | Compiler có thể biên dịch null check/dispatch theo cách khác; so sánh source và test. |
| Bytecode từ IDE khác CI | “Cùng source nên chắc chắn kết quả giống hệt” | Xác nhận compiler version, flags, annotation processor, bytecode instrumentation và artifact. |

## 14. Tự kiểm tra

**Bài 1.** Bạn cần biết một class file thực sự target Java 21 hay Java 17. Lệnh nào phù hợp, và cần đọc trường nào?

**Đáp án:** Dùng `javap -v ClassName`, xem **`major version`**. Giá trị `65` tương ứng Java 21; `61` tương ứng Java 17. Kiểm tra cùng với build toolchain và `--release`.

**Bài 2.** Bạn thấy `record Point(int x, int y)` và source dùng `case Point(int x, int y)`. Vì sao cần xem cả `Point.class` lẫn class chứa `switch`?

**Đáp án:** Class của `Point` cho biết record component, accessor và metadata `Record`; class chứa `switch` cho thấy logic dispatch, kiểm tra/khớp và cách gọi accessor khi phân loại. Chỉ xem một trong hai không đủ để hiểu toàn bộ đường đi.

**Bài 3.** Trong `javap -v` xuất hiện `BootstrapMethods` có `java.lang.runtime.SwitchBootstraps.typeSwitch`. Có phải mỗi pattern switch bắt buộc sinh đúng cùng một listing opcode ở mọi JDK?

**Đáp án:** Không. `typeSwitch` là cơ chế quan trọng có thể được `javac` sử dụng, nhưng dạng bytecode cụ thể không phải hợp đồng cú pháp nguồn. Compiler và cách hạ cú pháp có thể thay đổi miễn giữ ngữ nghĩa được đặc tả.

**Bài 4.** Tại sao một số tên biến xuất hiện khi compile `-g` nhưng biến mất trong output sau khi compile không có `-g`?

**Đáp án:** Tên và phạm vi biến cục bộ có thể nằm trong `LocalVariableTable` phục vụ debug. Không có metadata không chứng minh biến không tồn tại trong cách tính ở JVM.

**Bài 5.** Vì sao không kết luận record pattern chậm hơn chỉ bằng cách thấy bytecode có hai lời gọi accessor?

**Đáp án:** Bytecode là đầu vào cho runtime; JIT có thể inline/tối ưu, chi phí thực tế tùy workload. Cần benchmark/profiler và kiểm tra hành vi để đưa ra quyết định.

## 15. Checklist trước khi kết thúc điều tra

1. Đã xác minh `java`, `javac`, `javap` và `--release`/toolchain phù hợp?
2. Đã chạy thành công bài Java và xác minh **stdout** trước khi đọc disassembly?
3. Đã xem đúng **class file** của lần build cần phân tích, không phải file cũ?
4. Đã dùng `javap -c -p` cho phương thức chứa `instanceof`/record pattern/`switch`?
5. Đã dùng `javap -v` để kiểm tra `major version`, `Record`, `PermittedSubclasses` và `BootstrapMethods` khi liên quan?
6. Đã quote tên kiểu lồng có ký hiệu `$` khi chạy shell?
7. Nếu điều tra scope/debug, đã dùng `javac -g` và `javap -l` mà không đánh đồng debug range với quy tắc ngôn ngữ?
8. Đã phân biệt type pattern, record accessor, guard false, selector null và exception?
9. Đã tránh lấy số opcode làm kết luận tuyệt đối về performance?
10. Đã đưa kết quả phân tích trở lại **test hành vi và kiểm tra artifact build** thay vì chỉ nhìn listing bytecode?

## 16. Tài liệu tham khảo chính thức

- **Oracle JDK 21 `javap` tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **Oracle JDK 21 `javac` tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java Virtual Machine Specification 21 – Class File Format (`4):** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Java Language Specification 21 – Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch:** https://openjdk.org/jeps/441

**Ghi nhớ:** Sau compilation, `javap` giúp quan sát **class file version, bytecode, record metadata, sealed subtype và cơ chế dispatch**. Hãy liên hệ `instanceof`/`checkcast` với kiểm tra kiểu, accessor với deconstruction, `invokedynamic`/bootstrap với một số cách biên dịch `switch`, và debug tables với khả năng đối chiếu nguồn. Nhưng chỉ **compiler, test hành vi và profiling** cùng nhau mới trả lời đầy đủ câu hỏi “mã này đúng, tương thích và có đủ nhanh hay không”.
