# Quan sát mã được sinh cho `record` và `enum` bằng `javac` và `javap`

`record` và `enum` có cú pháp nguồn ngắn gọn, nhưng kết quả biên dịch chứa nhiều thành phần hơn những gì lập trình viên gõ trực tiếp: **field, constructor, accessor, phương thức tiện ích, metadata và bytecode khởi tạo**. Quan sát các thành phần đó giúp hiểu Java chuyển đổi cú pháp cấp cao thành class file ra sao, phương thức nào thật sự tồn tại ở runtime, và vì sao reflection hoặc framework nhìn thấy những thành viên “không có trong source”.

Bài này sử dụng **Java 17+** (biên dịch với `--release 17`) và công cụ `javap` đi kèm JDK để khảo sát **class file do `javac` tạo**, đồng thời phân biệt:

- **Hợp đồng ngôn ngữ:** những thành phần hoặc hành vi Java Language Specification (JLS) yêu cầu.
- **Chi tiết phát sinh ở bytecode:** cách một phiên bản `javac` cụ thể hiện thực hóa hợp đồng, có thể thay đổi giữa JDK.
- **Thông tin quan sát:** những gì `javap`, `javap -v` và Java Reflection phơi bày, không nhất thiết tương ứng một-một với một câu lệnh trong source.

Không nên xem output `javap` là source code gốc. Đây là bản trình bày cấu trúc/bytecode, không phải một trình decompiler tái tạo đầy đủ cú pháp Java.

## 1. Bộ công cụ kiểm tra và các mức quan sát

`javac` sinh `.class`; `javap` phân tích class file đã tạo. Cách làm tiêu chuẩn:

```sh
javac -version
javap -version
javac --release 17 -encoding UTF-8 -d out src/demo/Inspect.java
javap -classpath out demo.Point
javap -classpath out -p demo.Point
javap -classpath out -p -c demo.Point
javap -classpath out -p -v demo.Point
```

Ý nghĩa từng mức:

| Lệnh | Thông tin quan sát được |
| --- | --- |
| `javap -classpath out demo.Point` | Khai báo lớp cùng các thành viên public/protected hiện ra ở chế độ mặc định |
| `javap -p ...` | Hiện cả thành viên private; giúp thấy field chứa record component hoặc mảng enum constants |
| `javap -c ...` | Hiển thị bytecode của constructor/phương thức có phần code |
| `javap -v ...` | Phân tích class file chi tiết: version, flags, constant pool, method attributes, `Record` attribute, `BootstrapMethods`, `InnerClasses` khi có |
| `javap -s ...` | Hiển thị **JVM descriptors**, giúp phân biệt descriptor bytecode và chữ ký nguồn |
| `javap -l ...` | In bảng dòng/biến cục bộ nếu thông tin debug có trong class file |

`-classpath out` là **gốc cây class file**, không phải thư mục `out/demo`. Tên lớp truyền cho `javap` nên là tên đầy đủ như `demo.Point`. Option `-p` là viết tắt của `-private`, còn `-c` là disassemble bytecode; `-v` không giống “in nguồn Java gốc”.

`javap` có thể đọc trực tiếp đường dẫn `.class`, nhưng với project có package, chỉ định classpath root và tên lớp giúp tái hiện cách JVM tìm lớp. Nếu có nhiều phiên bản trên classpath, cần xác nhận đúng class file đang được đọc; cùng tên lớp nhưng khác output folder có thể dẫn đến hiểu nhầm.

> **Bản phát hành:** Với `--release 17`, class-file major version của những class biên dịch thành công ở đây là **61**. Lệnh `javap -v` có thể hiển thị `major version: 61`, ngay cả khi bạn chạy `javac` của một JDK mới hơn có hỗ trợ target 17.

## 2. Ví dụ chạy được: một `record`, một `enum`, một chương trình quan sát

Tạo tệp **`src/demo/Inspect.java`** với toàn bộ mã sau. Đây là một compilation unit có một lớp top-level `public` tên `Inspect`, cùng hai kiểu top-level package-private `Point` và `Level`; Java cho phép bố trí như vậy.

```java
package demo;

record Point(int x, int y) {
    int sum() {
        return x + y;
    }
}

enum Level {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Level(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}

public class Inspect {
    public static void main(String[] args) {
        Point point = new Point(2, 3);
        System.out.println(point.x() + "," + point.y());
        System.out.println(point.sum());
        System.out.println(point.equals(new Point(2, 3)));
        System.out.println(Point.class.isRecord());
        System.out.println(Point.class.getRecordComponents()[0].getName());

        System.out.println(Level.HIGH.weight());
        System.out.println(Level.values().length);
        System.out.println(Level.valueOf("LOW").name());
        System.out.println(Level.HIGH.ordinal());
        System.out.println(Level.class.isEnum());

        Level[] copy = Level.values();
        copy[0] = Level.HIGH;
        System.out.println(Level.values()[0].name());
    }
}
```

Từ **thư mục dự án**:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Inspect.java
java -cp out demo.Inspect
```

**Stdout chính xác** với mã này:

```text
2,3
5
true
true
x
3
3
LOW
2
true
LOW
```

Đầu ra của `javac` có ít nhất ba class file tương ứng ba kiểu top-level:

```text
out/
└── demo/
    ├── Inspect.class
    ├── Point.class
    └── Level.class
```

Ta **không** cần tự viết `Point.java` hay `Level.java`: các kiểu top-level không `public` đang nằm trong tệp `Inspect.java` đã được truyền trực tiếp cho `javac`. Tên `Point.class`, `Level.class` xuất hiện theo khai báo kiểu; thêm thành viên lồng nhau hoặc enum constant có class body có thể làm xuất hiện những class file phụ.

Lời gọi `Level.values()` trả về **mảng mới** chứa các hằng enum theo thứ tự khai báo. Việc thay `copy[0]` không sửa danh sách hằng enum thật; vì vậy dòng cuối vẫn in `LOW`.

## 3. `record`: từ header ngắn đến class có field, constructor và method

Khai báo:

```java
record Point(int x, int y) {
    int sum() {
        return x + y;
    }
}
```

Theo JLS 17, record class là một dạng **class đặc biệt, ngầm `final`, mở rộng `java.lang.Record`**. Header khai báo hai *record components*: `x` kiểu `int` và `y` kiểu `int`. Java yêu cầu các thành phần liên quan, dù không được viết trong source:

1. **Field tương ứng mỗi component:** `private final int x;` và `private final int y;`.
2. **Accessor public:** `public int x()` và `public int y()`, mang tên chính xác của component, khác convention JavaBean `getX()`.
3. **Canonical constructor:** nhận `(int x, int y)`, khởi tạo component fields. Constructor có thể khai báo tường minh hoặc dưới dạng compact constructor.
4. **`equals(Object)`, `hashCode()`, `toString()`:** nếu không tự khai báo tường minh, compiler cung cấp implementation suy ra từ components.
5. **Thành viên viết tay:** `int sum()` vẫn tồn tại với body do người viết định nghĩa.

`javap -classpath out -p demo.Point` thường hiển thị cấu trúc **tương đương về thành viên**:

```text
final class demo.Point extends java.lang.Record {
  private final int x;
  private final int y;
  demo.Point(int, int);
  int sum();
  public final java.lang.String toString();
  public final int hashCode();
  public final boolean equals(java.lang.Object);
  public int x();
  public int y();
}
```

Đây là **trích lược minh họa**, không phải cam kết rằng thứ tự dòng/định dạng của mọi phiên bản `javap` hoàn toàn giống nhau. Vì `Point` là top-level package-private, bản thân lớp và canonical constructor của ví dụ **không phải `public`**; các accessor lại `public` theo quy tắc record. Nếu khai báo `public record Point(...)` trong một file `Point.java` riêng, visibility và cách in của constructor thay đổi tương ứng.

### 3.1. Quan sát canonical constructor

Chạy:

```sh
javap -classpath out -p -c demo.Point
```

Với record này, phần constructor do compiler phát sinh thường có cấu trúc:

```text
Point(int, int):
  aload_0
  invokespecial java/lang/Record."<init>":()V
  aload_0
  iload_1
  putfield x:I
  aload_0
  iload_2
  putfield y:I
  return
```

Đoạn trên là **pseudo-disassembly rút gọn**: bản thực tế của `javap -c` còn có offsets như `0:`, chỉ số constant pool và định dạng JVM descriptors. Ý nghĩa quan trọng:

- `aload_0` nạp tham chiếu `this`.
- `invokespecial` gọi constructor cha `java.lang.Record`.
- `iload_1`/`iload_2` nạp tham số `int`; `putfield` ghi component fields.
- `return` kết thúc constructor.

**Đừng dùng offsets hay chỉ số constant pool** làm tiêu chí unit test cho một bản compiler bất kỳ. Các chi tiết nhỏ có thể thay đổi theo JDK và tối ưu hóa của compiler, trong khi ngữ nghĩa gán component và tính `final` phải được bảo toàn.

### 3.2. Quan sát accessor và phương thức tự viết

Phương thức `x()` ngầm sinh ra thường có bytecode tương đương:

```text
aload_0
getfield x:I
ireturn
```

Tức là nó đọc field `x` của instance rồi trả về số nguyên. Phương thức `sum()` là phần **người dùng viết**, nhưng vẫn được compiler chuyển thành bytecode cộng hai giá trị `int`, thường gồm `getfield`, `iadd`, `ireturn`. Quan sát giúp phân biệt “method tự sinh” với “method trong source”, nhưng bytecode của một phương thức không mang một nhãn đơn giản nói nó do người viết hay compiler sinh ra.

### 3.3. `equals`, `hashCode`, `toString`: cơ chế `invokedynamic` trong `javac`

Ở các bản `javac` OpenJDK hiện đại, ba method ngầm sinh thường có body ngắn chứa instruction **`invokedynamic`**, với bootstrap liên quan tới **`java.lang.runtime.ObjectMethods.bootstrap`**. Kiểm tra:

```sh
javap -classpath out -p -c demo.Point
javap -classpath out -p -v demo.Point
```

Một mẫu ý nghĩa trong disassembly:

```text
toString()  -> invokedynamic ... toString(...)
hashCode()  -> invokedynamic ... hashCode(...)
equals(o)   -> invokedynamic ... equals(...)
```

Đây là **sơ đồ minh họa**, không phải log `javap` nguyên văn. Ở `-v`, mục `BootstrapMethods` có thể cho thấy `java.lang.runtime.ObjectMethods.bootstrap` và các handle tới component fields. Khi chạy, bootstrap hỗ trợ tạo logic cho các phương thức cốt lõi của record.

Quan trọng hơn cơ chế nội bộ là **hợp đồng ngôn ngữ**:

- `equals` ngầm sinh so sánh record cùng kiểu và các giá trị component theo quy tắc record.
- `hashCode` phụ thuộc những component đó và tuân thủ hợp đồng hash/equality.
- `toString` trình bày tên record, tên component và giá trị theo cách dễ đọc.

**Không dựa vào bytecode `invokedynamic` như một yêu cầu của mọi compiler.** JLS yêu cầu hành vi record nhưng không buộc mọi compiler hiện thực `equals/hashCode/toString` bằng cùng chuỗi bytecode hoặc cùng bootstrap. Định dạng chính xác của `toString` cũng không nên bị parse như một serialization format ổn định.

### 3.4. `Record` attribute và thông tin reflection

Chạy:

```sh
javap -classpath out -v demo.Point
```

Class file có **`Record` attribute** mô tả danh sách component của record, bao gồm tên và descriptor, cùng các attribute liên quan như signature/annotations nếu có. Một phần ý nghĩa thường đọc được là:

```text
Record:
  int x;
    descriptor: I
  int y;
    descriptor: I
```

Đây là phần trình bày *rút gọn* cho record đơn giản; ngoài các dòng đó còn nhiều mục thông tin class file khác.

Reflection sử dụng metadata để xác định record và component:

```java
System.out.println(Point.class.isRecord());
System.out.println(Point.class.getRecordComponents()[0].getName());
```

Hai dòng trên là **mảnh trích từ chương trình hoàn chỉnh ở mục 2** và cho kết quả `true`, `x`. `Class::getRecordComponents` trả về thông tin `RecordComponent`, không phải mảng Field: component metadata, field và accessor là các khái niệm liên quan nhưng không đồng nhất.

**Không nhầm giữa `Record` attribute và một cờ JVM tưởng tượng tên `ACC_RECORD`.** Tính chất record được thể hiện qua cấu trúc class file và metadata được quy định; khi xem flags của `javap -v`, không nên đi tìm một `ACC_RECORD` bắt buộc trong `access_flags` của `ClassFile`. Record vẫn là class đặc biệt trong ngôn ngữ.

### 3.5. Chỗ người viết có thể thay đổi code được sinh

`record` không bắt buộc dùng body canonical constructor mặc định. Có thể xác thực dữ liệu trong compact constructor:

```java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }
}
```

Đây là **ví dụ độc lập**: hãy lưu trong `Range.java` nếu muốn biên dịch riêng, hoặc đặt cùng package như một top-level type không `public`. Sau kiểm tra, compiler vẫn thực hiện khởi tạo component fields theo quy tắc compact constructor. Khi xem `javap -c`, constructor giờ có thêm bytecode kiểm tra điều kiện và ném exception.

Record cũng có thể khai báo tường minh accessor hoặc `equals/hashCode/toString` theo các quy tắc hợp lệ. Khi đó `javac` không cần sinh implementation mặc định cho chính phương thức đã khai báo. Hợp đồng mô hình dữ liệu của record vẫn đáng được tôn trọng, đặc biệt tính chất dữ liệu “tái tạo từ accessor values thì equals tương đương”.

**Giới hạn quan trọng:** Record không được khai báo thêm instance fields tùy ý ngoài component fields được ngôn ngữ sinh, nhưng có thể có static fields, static methods, instance methods và những thành phần hợp lệ khác. Record cũng không mở rộng class tự chọn vì đã kế thừa `java.lang.Record` và ngầm `final`.

## 4. `enum`: từ danh sách hằng đến class đặc biệt

Khai báo trong ví dụ:

```java
enum Level {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Level(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
```

Một enum class **mở rộng `java.lang.Enum<Level>`**. Nó có ba đối tượng hằng đã định nghĩa, được tạo trong quá trình khởi tạo class. Vì enum ví dụ **không** có constant-specific class bodies, enum class này có dạng ngầm **`final`**. Nếu enum có constant-specific class bodies, các quy tắc subclass/sealed của enum khác đi; không áp dụng câu “mọi enum luôn là class final” cho mọi trường hợp.

### 4.1. Thành viên do `javac` cung cấp

| Thành phần | Ý nghĩa | Nguồn gốc |
| --- | --- | --- |
| `LOW`, `MEDIUM`, `HIGH` | Mỗi constant là một instance duy nhất được đặt tên | Do khai báo enum constants; compiler tạo các static fields tương ứng |
| `private static final Level[] ...` | Mảng chứa toàn bộ constants, dùng làm backing store | Chi tiết triển khai, tên thường là `$VALUES` trên OpenJDK |
| `public static Level[] values()` | Trả về các constants theo thứ tự khai báo, trong mảng mới | Method ngầm được ngôn ngữ bảo đảm |
| `public static Level valueOf(String name)` | Lấy constant đúng tên khai báo | Method ngầm được ngôn ngữ bảo đảm |
| Constructor của `Level` | Tạo constants và gán `weight` | Do người dùng khai báo, nhưng compiler điều chỉnh ở bytecode |
| `<clinit>` | Khởi tạo static fields và bộ constants | Static initializer của class file |
| `weight` và `weight()` | Trạng thái, hành vi riêng người viết | Không phải toàn bộ tự sinh |
| `name()`, `ordinal()` | Truy cập tên và thứ tự khai báo | **Kế thừa** từ `java.lang.Enum`, không phải mỗi enum tự khai báo lại |

Điểm dễ nhầm: `values()` và `valueOf(String)` là **static methods của chính kiểu `Level`** được ngôn ngữ cung cấp; `name()` và `ordinal()` là **instance methods được kế thừa từ `Enum`**.

### 4.2. Quan sát các field và method không có trong source

Chạy:

```sh
javap -classpath out -p demo.Level
javap -classpath out -p -c demo.Level
javap -classpath out -p -v demo.Level
```

Một bản `javap -p` trên OpenJDK thường cho thấy cấu trúc tương đương:

```text
final class demo.Level extends java.lang.Enum<demo.Level> {
  public static final demo.Level LOW;
  public static final demo.Level MEDIUM;
  public static final demo.Level HIGH;
  private final int weight;
  private static final demo.Level[] $VALUES;
  public static demo.Level[] values();
  public static demo.Level valueOf(java.lang.String);
  private demo.Level(int);
  int weight();
  private static demo.Level[] $values();
  static {};
}
```

**Đây là trích lược minh họa**; chi tiết cách hiển thị tham số constructor, tên `$VALUES`, helper `$values()` và thứ tự thành viên **phụ thuộc compiler/JDK**. Đặc biệt, bytecode constructor có thêm tham số ẩn tên và ordinal; một số chế độ hiển thị của `javap` có thể khác nhau ở chữ ký dễ đọc.

Các hằng enum được biểu diễn bằng static fields có dấu `ACC_ENUM` trong class file. Mảng nội bộ như `$VALUES` có thể mang dấu `ACC_SYNTHETIC`, cho biết đó là thành viên do compiler thêm cho nhu cầu triển khai. Dấu `ACC_SYNTHETIC` **không** phải là chỉ báo duy nhất để tìm mọi thứ “sinh tự động”: các method được JLS ngầm khai báo như `values()` vẫn là API được phép gọi bình thường.

### 4.3. `<clinit>` và quá trình tạo hằng enum

Đoạn mã Java:

```java
LOW(1), MEDIUM(2), HIGH(3)
```

được compile thành logic tương đương:

1. Tạo instance `LOW` với thông tin tên `"LOW"`, ordinal `0` và tham số người dùng `1`.
2. Tạo `MEDIUM` với tên `"MEDIUM"`, ordinal `1` và `2`.
3. Tạo `HIGH` với tên `"HIGH"`, ordinal `2` và `3`.
4. Gán các static fields và tạo backing array chứa ba hằng để phục vụ `values()`.

Logic này thường nằm trong class initialization method **`<clinit>`**, có thể xem bằng `javap -c -p demo.Level`. Một dạng pseudo-bytecode:

```text
new Level
dup
ldc "LOW"
iconst_0
iconst_1
invokespecial Level.<init>(String, int, int)
putstatic Level.LOW
...
putstatic Level.$VALUES
return
```

**Đoạn trên không phải output nguyên văn** của một JDK cụ thể. Các opcode tạo số nguyên, constant-pool indexes, helper tạo array và thứ tự chỉ thị có thể khác nhau. Quy tắc ngôn ngữ quan trọng là các constants được khởi tạo theo trình tự khai báo, có tên/ordinal tương ứng.

Constructor ở source chỉ khai báo `Level(int weight)`. Trong class file do `javac` tạo, constructor cần thêm tham số dùng để gọi constructor của `java.lang.Enum`, về bản chất là **`(String name, int ordinal, int weight)`**. JVM descriptor tương ứng là **`(Ljava/lang/String;II)V`**. Người dùng Java **không được** gọi constructor enum để tạo constants mới từ source, và không được viết constructor `public` hoặc `protected` cho enum.

### 4.4. `values()`, `valueOf()` và sao chép mảng

Trong enum `Level`:

- `values()` trả về **một mảng mới** theo thứ tự `LOW`, `MEDIUM`, `HIGH`. Implementation OpenJDK thường trả clone của backing array, nên sửa mảng từ `values()` không đổi các constants của enum.
- `valueOf("LOW")` trả về chính `Level.LOW`; tên phải khớp **chính xác** ký tự, phân biệt hoa thường, không cắt khoảng trắng.
- `Level.valueOf("MISSING")` ném `IllegalArgumentException`; gọi với null ném `NullPointerException`.
- `name()` trả đúng tên `LOW`/`MEDIUM`/`HIGH` theo `Enum`, trong khi `toString()` có thể được enum override để in tên thân thiện hơn.
- `ordinal()` là vị trí khai báo, bắt đầu từ 0. **Không dùng ordinal làm mã dữ liệu nghiệp vụ hoặc lưu lâu dài**, vì đổi thứ tự constants làm đổi ordinal.

Một phần disassembly thường thấy:

```text
values()  -> getstatic backing-array; invokevirtual clone; checkcast; areturn
valueOf(String) -> ldc Level.class; aload_0; invokestatic Enum.valueOf; checkcast Level; areturn
```

Đây là **sơ đồ hành vi bytecode điển hình**, không phải guarantee mọi JVM/compiler phải có y hệt instruction sequence. `javap -c -p` dùng để xem implementation thực sự của JDK bạn đang chạy.

### 4.5. Enum có constant-specific class body

Xem ví dụ **độc lập** sau:

```java
enum Operation {
    ADD {
        @Override int apply(int a, int b) {
            return a + b;
        }
    },
    MUL {
        @Override int apply(int a, int b) {
            return a * b;
        }
    };

    abstract int apply(int a, int b);
}
```

Lưu trong tệp `Operation.java` và chạy:

```sh
javac --release 17 -d out Operation.java
javap -classpath out -p Operation
```

Ở trường hợp này, mỗi constant có class body có thể tạo **class file con** như `Operation$1.class`, `Operation$2.class` trong cách biên dịch OpenJDK, với phương thức `apply` riêng. Class enum tổng thể có quan hệ kế thừa khác ví dụ `Level` không có constant bodies; trong Java 17 nó **ngầm sealed** khi có ít nhất một constant có class body, thay vì ngầm final. Không suy luận rằng source có một enum thì chỉ phát sinh một class file.

Không phải mọi enum đều có `$values()` hoặc cùng tên helper: đây là chi tiết phụ thuộc implementation. Hợp đồng `values()`/`valueOf(String)` được JLS xác định và mới là điều code ứng dụng có thể dựa vào.

## 5. So sánh record và enum trên class file

| Tiêu chí | `record Point(int x, int y)` | `enum Level { LOW, MEDIUM, HIGH }` |
| --- | --- | --- |
| Superclass | `java.lang.Record` | `java.lang.Enum<Level>` |
| Mục đích cú pháp | Carrier minh bạch của bộ component cố định | Tập instance có tên, hữu hạn theo constants khai báo |
| Trạng thái | Field private final tương ứng component | Static fields chứa constants; có thể có instance fields riêng |
| Constructor | Canonical constructor theo record header | Constructor bị kiểm soát; compiler bổ sung tên và ordinal |
| Method được ngầm cung cấp | Component accessors, `equals`, `hashCode`, `toString` khi không khai báo tường minh | `values()` và `valueOf(String)` |
| Method kế thừa cần nhớ | Các thành viên từ `Record`/`Object` | `name()`, `ordinal()`, `compareTo()` từ `Enum` |
| Metadata cần kiểm tra | `Record` class-file attribute, component descriptors | `ACC_ENUM`, constant fields, static initialization; metadata tổng hợp theo compiler |
| Hành vi `equals` | Thông thường dựa vào component values theo hợp đồng record | Enum instances dùng identity equality (các constants là đối tượng duy nhất) |
| Chế độ `final` | Record class luôn ngầm final | Enum không có constant class body ngầm final; có constant body có quy tắc sealed |
| Cạm bẫy | Tưởng accessor là `getX()`, tưởng record là deep immutable | Tưởng ordinal là mã ổn định, tưởng `values()` trả backing array |

**Record không đồng nghĩa deep immutability:** Các component fields là `final` nhưng nếu component là `List` hoặc array có thể thay đổi, nội dung bên trong object tham chiếu vẫn có thể bị sửa. Bản compiler sinh không tự động defensive copy.

**Enum constants là các instance:** Không phải chuỗi hoặc số nguyên được `javac` thay thế đơn giản ở mọi nơi. `name()` và `ordinal()` là metadata của instance enum thực sự.

## 6. Cách đọc `javap -v` mà không nhầm metadata với source

Output verbose có nhiều phần. Đọc theo thứ tự:

1. **Header:** class name, superclass, class-file version, flags. Record extends `java.lang.Record`, enum extends `java.lang.Enum`.
2. **Fields:** xác định các component fields của record, enum constant fields và backing fields; để ý `ACC_FINAL`, `ACC_PRIVATE`, `ACC_STATIC`, `ACC_ENUM`, `ACC_SYNTHETIC` khi có.
3. **Methods:** constructors, accessors, `values`, `valueOf`, `equals`/`hashCode`/`toString`. Dùng `-p` để không bỏ qua private members.
4. **`Code` attributes:** kiểm tra `getfield`/`putfield` trong record, `<clinit>` trong enum, `invokedynamic` trong những implementation record sử dụng bootstrap.
5. **`Record` attribute:** tên và descriptors của record components. Không nhầm với danh sách instance fields tự viết.
6. **`BootstrapMethods`:** nếu có, tra những liên kết như `ObjectMethods.bootstrap`; `invokedynamic` ở class file không có nghĩa có compiler tùy biến hay annotation processor.
7. **`InnerClasses`, `NestMembers`, `Signature`, runtime annotations, debug tables:** xuất hiện khi phù hợp với code/JDK; không phải thành phần bắt buộc của mọi ví dụ.

Đừng sao chép **constant-pool index** dạng `#7`, thứ tự instructions hay mã SHA từ một bản `javap` để làm bài kiểm tra tính đúng đắn chung. Chúng phụ thuộc compiler, release, options và cách serialize class file. Hãy kiểm tra **cấu trúc/ngữ nghĩa**: superclass, method descriptors, access flags cần thiết, method existence và hành vi runtime.

### Synthetic và implicit khác nhau ra sao?

- **Implicitly declared:** JLS coi phương thức/thành viên là được khai báo ngầm trong ngôn ngữ, có thể được code Java gọi như `Point.x()` hoặc `Level.values()`.
- **Synthetic:** `ACC_SYNTHETIC` ở class-file level chỉ ra thành viên được compiler tạo và không tương ứng trực tiếp một khai báo source thông thường, thường là helper triển khai.
- **Mandated:** Một số metadata/parameters của class file có thể mang ý nghĩa được ngôn ngữ bắt buộc; không được đồng nhất mọi thành viên compiler thêm với synthetic flags.

Vì vậy, một phương thức **sinh ngầm nhưng public theo hợp đồng** có thể không mang `ACC_SYNTHETIC`, còn một mảng helper riêng của enum có thể mang flag đó. Không dùng “có synthetic = được sinh, không synthetic = do người viết” như quy tắc tuyệt đối.

## 7. Quan sát qua Reflection: hai nguồn thông tin bổ trợ

`javap` cho biết **class file và bytecode**, Reflection cho thấy phần của cấu trúc kiểu được JVM phơi bày khi chạy:

```java
Point.class.isRecord()
Point.class.getRecordComponents()
Point.class.getDeclaredFields()
Level.class.isEnum()
Level.class.getEnumConstants()
Level.class.getDeclaredMethods()
```

Đoạn trên là **danh sách biểu thức minh họa**, không phải chương trình Java đầy đủ. Với `Point` và `Level` của mục 2:

- `Point.class.isRecord()` là `true`.
- `Point.class.getRecordComponents()` trả về hai record components, lần lượt là `x` và `y`.
- `Level.class.isEnum()` là `true` và `Level.class.getEnumConstants()` cung cấp ba constants.
- `getDeclaredFields()`/`getDeclaredMethods()` có thể chứa cả những thành viên do compiler sinh; dùng `Field.isSynthetic()` hoặc `Method.isSynthetic()` để kiểm tra từng thành viên thay vì đoán bằng tên.

**Thứ tự mảng các declared fields/methods từ Reflection không được bảo đảm ổn định** như thứ tự khai báo source; không viết bài kiểm tra phụ thuộc thứ tự hoặc tên helper nội bộ. Ngược lại, **thứ tự phần tử trong `values()` và `getEnumConstants()`** tương ứng thứ tự khai báo enum constants.

Record component reflection **không** có nghĩa component field là public. Nó mô tả component qua API riêng, còn field chứa component vẫn là `private final`.

## 8. Các bài thực hành thay đổi source để so sánh output

### Thí nghiệm A — Thêm component vào record

Thay `record Point(int x, int y)` thành:

```java
record Point(int x, int y, int z) {
    int sum() {
        return x + y + z;
    }
}
```

Đây là **mảnh thay đổi source, không chạy kèm nguyên chương trình ở mục 2 nếu chưa sửa `new Point(2, 3)`**. Sau khi cập nhật lời gọi thành `new Point(2, 3, 4)`, biên dịch và so sánh:

- Số component fields tăng từ 2 lên 3.
- Canonical constructor thay từ `(II)V` sang `(III)V`.
- Accessor `z()` và mục `z` trong `Record` attribute xuất hiện.
- Logic mặc định của `equals`/`hashCode`/`toString` nay tính đến cả `z`.

**Chú ý API compatibility:** Code cũ gọi constructor hai tham số sẽ không còn compile nếu không có overload tương thích. Thay record header là thay đổi hợp đồng public có thể phá client code.

### Thí nghiệm B — Thêm constant vào enum

Thay:

```java
LOW(1), MEDIUM(2), HIGH(3);
```

thành:

```java
LOW(1), MEDIUM(2), HIGH(3), CRITICAL(4);
```

Đây là **mảnh chỉnh enum `Level`, không phải file Java độc lập**. Sau biên dịch:

- `values().length` tăng từ 3 lên 4.
- `Level.valueOf("CRITICAL")` trở thành hợp lệ.
- Một static field `CRITICAL` xuất hiện và `<clinit>` cần khởi tạo constant đó.
- Ordinal các constants cũ không đổi nếu chỉ thêm ở cuối; chèn một constant ở giữa sẽ đổi ordinal của những constant phía sau.
- Có thể có thay đổi helper/array bytecode để chứa bốn constants; đừng viết test theo tên helper.

Đây là lý do **không serialize enum bằng ordinal**. Với persistence/API lâu dài, nên dùng mã định danh độc lập hoặc quy ước tên có kiểm soát.

### Thí nghiệm C — Thêm body cho một enum constant

Ví dụ `Operation` ở mục 4.5 là case quan trọng: lệnh `javac` có thể tạo các class file như `Operation$1.class`. Dùng:

```sh
javap -classpath out -p -c 'Operation$1'
```

Dấu nháy đơn ở đây là cú pháp tiện lợi cho **shell Unix** nhằm ngăn mở rộng `$1`. Trên PowerShell cũng có thể dùng chuỗi đơn nháy; còn trong Windows `cmd.exe` có quy tắc escape/quote khác. Trước hết hãy **liệt kê file thật sự được tạo** và truyền tên lớp phù hợp với tool/shell đang sử dụng. Tên lớp có `$`, nếu xuất hiện, là binary-name của class nội bộ trong một implementation.

### Thí nghiệm D — Viết explicit record accessor

Tạo file `RecordAccessor.java` độc lập:

```java
record Temperature(int celsius) {
    @Override
    public int celsius() {
        return celsius;
    }
}

public class RecordAccessor {
    public static void main(String[] args) {
        Temperature t = new Temperature(20);
        System.out.println(t.celsius());
    }
}
```

Chạy:

```sh
javac --release 17 -d out RecordAccessor.java
java -cp out RecordAccessor
```

Stdout:

```text
20
```

Trong `javap -c -p Temperature`, vẫn có accessor `celsius()` nhưng **body của method này là do source cung cấp**, thay vì accessor mặc định do compiler tạo. Bản chất record không đổi. Không được thêm accessor `getCelsius()` rồi tưởng đó thay thế component accessor bắt buộc; `celsius()` vẫn là tên theo record header.

## 9. Những sai lầm khi đọc mã được sinh

**“`record` chỉ là class có getter.”** Không đủ. Record có metadata `Record`, canonical constructor, các component fields private final, component accessors và hợp đồng `equals/hashCode/toString`, đồng thời không có setter mặc định. Hành vi equality trên components là một phần quan trọng của cú pháp record.

**“`record` luôn immutable sâu.”** Sai. Reference component có thể trỏ tới một cấu trúc dữ liệu mutable; field `final` chỉ ngăn gán lại reference sau khởi tạo.

**“`enum` chỉ là int hoặc String constants.”** Sai. Mỗi constant là một instance kiểu enum; `Enum` quản lý `name`/`ordinal`, compiler sinh field và code khởi tạo.

**“`Level.values()` trả về trực tiếp mảng nội bộ.”** Sai theo hợp đồng phương thức: mảng trả về mới, thay đổi mảng đó không làm mất/đổi constants thực sự.

**“`name()`, `ordinal()`, `values()` và `valueOf()` đều do compiler sinh trong mỗi enum.”** Sai. Hai phương thức đầu là inherited instance methods của `Enum`; hai phương thức sau được implicitly declared ở mỗi enum.

**“Mọi enum đều `final`.”** Sai khi có constant-specific class bodies; trong Java 17 có các quy tắc enum implicitly sealed.

**“`javap -c` cho lại source Java gốc.”** Sai. Nó hiển thị bytecode và signatures; cấu trúc lexical/formatting, nhiều lựa chọn compiler và source sugar đã mất.

**“Thấy `invokedynamic` ở record tức là Java bắt buộc mọi compiler triển khai thế.”** Sai. Đây là cách phổ biến của `javac`/OpenJDK, còn JLS yêu cầu ngữ nghĩa `equals/hashCode/toString`.

**“Không có flag `ACC_SYNTHETIC` thì chắc chắn lập trình viên viết method đó.”** Sai. Thành viên được khai báo ngầm bởi ngôn ngữ và helper triển khai là hai loại khác nhau; synthetic flag không đủ để kết luận nguồn gốc.

**“Cứ thấy `$VALUES` là API public có thể dựa vào.”** Sai. Tên backing field/helper là implementation detail, thay đổi theo compiler và release. API ổn định là `values()` và `valueOf(String)`.

**“Khi biên dịch một file Java chỉ có một class file.”** Sai: một source file có thể chứa nhiều top-level types, nested types, enum constants với class bodies, v.v.

## 10. Checklist kiểm chứng lớp được sinh

1. **Đầu vào đã đúng?** Ghi nhận tệp nguồn, `javac -version` và đường dẫn output của lần compile; tránh đọc nhầm `.class` cũ.
2. **Target class file?** Dùng `--release 17`, kiểm tra major version 61 bằng `javap -v`.
3. **Record:** xác nhận extends `Record`, component fields, canonical constructor, accessor methods và `Record` attribute.
4. **Record methods:** phân biệt method viết tay với ngầm sinh; kiểm tra `equals/hashCode/toString` và chỉ coi `invokedynamic/ObjectMethods` là một cách hiện thực có thể quan sát.
5. **Enum:** xác nhận extends `Enum`, constant fields, `values()`/`valueOf(String)`, constructor thêm tên/ordinal và `<clinit>`.
6. **Compiler-generated helpers:** dùng `-p -v` để xem flags/synthetic metadata, không dựa vào tên như `$VALUES` làm hợp đồng.
7. **Runtime:** chạy chương trình với classpath đúng, kiểm tra kết quả của accessor/equality/enum methods; dùng Reflection để hiểu sự khác nhau giữa class-file metadata và runtime model.
8. **Thay đổi source:** khi thêm component/constant/constant body, so sánh output từ hai lần build sạch. Không dựa vào thứ tự constant pool hoặc từng byte instruction trong bài test ngữ nghĩa.

**Ghi nhớ:** Cú pháp `record` và `enum` là những cam kết cấp **ngôn ngữ Java**. `javac` hiện thực hóa chúng bằng class files, còn `javap` cho phép nhìn thấy fields, methods, metadata và bytecode. Hãy học cấu trúc được chuẩn yêu cầu, rồi dùng bytecode để giải thích cơ chế; không biến tên helper hoặc opcode cụ thể thành API của ứng dụng.

## Tài liệu đối chiếu

- Java Language Specification 17, **`8.10 Record Classes** và **`8.9 Enum Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- Oracle JDK 17, **The javap Command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Java SE 17 API, **`java.lang.Record`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
- Java SE 17 API, **`java.lang.Enum`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
- Oracle Java Tutorials, **Record Classes**: https://docs.oracle.com/en/java/javase/17/language/records.html
- dev.java, **Working with Enumerations** (Reflection): https://dev.java/learn/reflection/enums/