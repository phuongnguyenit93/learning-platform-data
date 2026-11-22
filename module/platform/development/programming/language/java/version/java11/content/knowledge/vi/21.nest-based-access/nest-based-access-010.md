# Kiểm tra bytecode bằng `javap` để hiểu Nest-based access trong Java 11

## 1. Mục tiêu bài học

Một lớp Java có thể khai báo các lớp lồng bên trong, ví dụ `Outer.Inner` hoặc `Outer.StaticMember`. Các lớp ấy trông như một khối mã nguồn nhưng được biên dịch thành **những classfile độc lập**. Vậy Java Virtual Machine (JVM) làm thế nào để biết các lớp đó được phép truy cập `private` của nhau?

Từ **Java 11 (JEP 181 — Nest-Based Access Control)**, JVM hiểu khái niệm **nest**: một nhóm lớp/interface có một **nest host** chung và có thể truy cập `private` của nhau theo quy tắc JVM. `javac` đánh dấu quan hệ này bằng các thuộc tính classfile **`NestMembers`** và **`NestHost`**. Công cụ `javap` cho phép bạn **đọc classfile thật** để xác minh hai thuộc tính ấy và xem các lệnh bytecode được tạo.

Sau bài học, bạn có thể:

1. Phân biệt lớp lồng nhau ở **Java source** với **nestmate ở JVM**.
2. Biên dịch ví dụ Java 11 bằng `javac --release 11`.
3. Sử dụng `javap -v` để tìm `major version: 55`, `NestMembers` và `NestHost`.
4. Sử dụng `javap -c -p` để xem `getfield` và lệnh gọi phương thức `private` **trực tiếp**, thay vì suy đoán từ mã nguồn.
5. Phân biệt `InnerClasses`/`EnclosingMethod` với hai thuộc tính xác định quyền truy cập nest.
6. Đối chiếu kết quả bằng `Class.getNestHost()`, `getNestMembers()` và `isNestmateOf()`.
7. Chẩn đoán lỗi khi đóng gói JAR, chuyển đổi bytecode, chạy khác target JDK hoặc class loader không khớp.
8. Viết kiểm thử đơn giản để ngăn bộ công cụ build/obfuscator làm mất nest metadata.

**Phạm vi:** đây là tính năng có từ Java 11 và vẫn được dùng trong các JDK hiện đại. Bài tập chủ yếu kiểm tra **classfile Java 11**, không hướng dẫn cách tiếp tục dùng workaround đã lỗi thời. Mã mẫu có thể biên dịch bằng JDK 11 hoặc JDK mới khi chọn `--release 11`.

## 2. Ba lớp khái niệm: source, classfile, runtime

| Tầng | Ta nhìn thấy gì? | Công cụ/đặc tả |
| --- | --- | --- |
| **Java source** | `private class` lồng, `static class` lồng, inner class, local/anonymous class | `javac` và quy tắc ngôn ngữ Java |
| **Classfile** | Các file `Outer.class`, `Outer$Inner.class`; metadata `NestMembers`/`NestHost`; bytecode `getfield`/`invokevirtual` | `javap -v`, `javap -c -p`, JVMS |
| **JVM runtime** | JVM kiểm tra quan hệ nestmate khi truy cập `private` và tải/liên kết lớp | JVMS `5.4.4`, `Class.getNestHost()`, `Class.isNestmateOf()` |

Mỗi file `.class` chứa định nghĩa **một** lớp hoặc interface. Một khai báo `Outer` kèm hai lớp lồng thường tạo ra ít nhất:

```text
Outer.class
Outer$StaticMember.class
Outer$Inner.class
```

Ký tự `$` ở đây là **quy ước tên nhị phân phổ biến do `javac` tạo ra**, không phải bằng chứng chắc chắn một lớp là nestmate. Quan hệ được xác định từ metadata classfile và kiểm tra runtime, không phải vì hai tên tình cờ có cùng prefix.

**Nest host:** trong ví dụ thông thường, đó là lớp ngoài cùng như `Outer`.

**Nest member:** lớp cùng nest, chẳng hạn `Outer$StaticMember` và `Outer$Inner`. Nest host **cũng là thành viên của chính nest đó**.

**Nestmate:** hai lớp có cùng nest host đã được xác định hợp lệ. Nestmates được phép truy cập `private` của nhau ở tầng JVM. Điều này **không** cho phép một lớp top-level hoàn toàn khác trong cùng package tự động truy cập `private`.

## 3. JEP 181 giải quyết điều gì?

Java source đã có quy tắc cho phép một lớp lồng truy cập thành viên `private` của lớp ngoài, và ngược lại. Nhưng vì chúng được biên dịch thành nhiều file `.class`, JVM phải có cách thực thi quy tắc mà không coi mọi lớp trong cùng package là một thực thể.

JEP 181 giới thiệu:

- **`NestMembers`:** khai báo ở **nest host**, liệt kê tên các lớp/interface khác được chủ thể host cho phép làm thành viên.
- **`NestHost`:** khai báo ở một **nest member không phải host**, chỉ ra nest host mà member khẳng định nó thuộc về.
- **Kiểm tra hai phía**: member chỉ nói `NestHost=Outer` chưa đủ; host còn phải cho phép member qua `NestMembers`, và quan hệ phải thỏa điều kiện runtime package.
- **Quy tắc JVM mới** cho phép bytecode từ nestmate truy cập các field/method/constructor `private` phù hợp.

Điều này giúp `javac` Java 11 biên dịch nhiều lần truy cập `private` thành truy cập trực tiếp, **không cần sinh các accessor bridge có tên dạng `access$...` chỉ để bắc cầu private access**.

Đây **không phải** thay đổi quyền truy cập ở mức ngôn ngữ: code từ một lớp top-level ngoài nest vẫn không thể đọc `private` chỉ vì ở cùng thư mục, cùng package hay có tên giống nhau. Đồng thời, **không phải mọi thành phần `synthetic` biến mất**: inner class không static vẫn có thể cần field `this$0` tham chiếu outer instance.

## 4. Công cụ `javap`: chọn đúng tùy chọn

`javap` là công cụ đi kèm JDK để xem cấu trúc và disassemble classfile. Trong Java SE 11, các option cơ bản:

| Lệnh/tùy chọn | Chức năng | Dùng khi |
| --- | --- | --- |
| `javap SomeClass` | Hiển thị chữ ký thành viên public/protected/package theo mặc định | Xem nhanh giao diện class |
| `javap -p SomeClass` | Hiện cả `private` | Xác nhận method/field private thực sự tồn tại |
| `javap -c SomeClass` | Disassemble lệnh bytecode của các method được hiển thị | Xem các lệnh `getfield`, `invokevirtual` |
| `javap -c -p SomeClass` | Bytecode **kèm method private** | Đối chiếu trực tiếp private access giữa nestmates |
| `javap -v SomeClass` | Chi tiết classfile, constant pool, version, flags, attributes | Tìm `NestHost`, `NestMembers`, `InnerClasses` |
| `javap -v -p SomeClass` | Kết hợp metadata và thành viên private | Khám phá classfile đầy đủ |
| `javap -s SomeClass` | JVM descriptors kiểu dữ liệu | Khi cần giải thích `I`, `Ljava/lang/String;` |
| `javap -l SomeClass` | Line/local-variable tables nếu được biên dịch kèm debug info | Đối chiếu lệnh với dòng Java |
| `javap -cp DIR SomeClass` | Chọn đúng classpath | Tránh vô tình xem bản `.class` khác |
| `javap --module MOD ClassName` | Chọn lớp trong module tương ứng | Khi điều tra ứng dụng/module JDK |

Không cần cài decompiler thứ ba chỉ để làm bài này. `javap` **không chạy bytecode** và không chứng minh một ứng dụng đã liên kết/tải class thành công lúc runtime. Nó đọc thông tin classfile.

### 4.1. Vì sao nên dùng cả `-v` lẫn `-c -p`?

- `-v` trả lời: **“Ai là host, ai là member, phiên bản classfile nào?”**
- `-c -p` trả lời: **“Method private chứa các lệnh bytecode gì, có gọi trực tiếp field/method của lớp còn lại không?”**
- `-p` đặc biệt quan trọng vì một số method cần kiểm tra là `private`, sẽ không hiện ra trong chế độ hiển thị mặc định.
- `-v` có thể in rất nhiều dòng constant pool và bootstrap methods; hãy tập trung vào **khối attributes ở cuối** và method đang quan tâm.

Không kết luận chỉ từ dòng `InnerClasses`. Thuộc tính `InnerClasses` mô tả cấu trúc nested class; **không phải** thay thế cho quyền truy cập `NestHost`/`NestMembers`.

## 5. Chương trình Java 11 hoàn chỉnh để thực hành

Tạo một thư mục trống, rồi tạo file đúng tên **`NestBytecodeDemo.java`** với mã sau. Đây là chương trình **chạy độc lập**; nó gồm một lớp public và một lớp top-level khác để chứng minh cùng package **không đồng nghĩa** cùng nest.

```java
import java.util.Arrays;

public class NestBytecodeDemo {
    private int secret = 40;

    private String label() {
        return "ready";
    }

    private static class Probe {
        private int read(NestBytecodeDemo owner) {
            return owner.secret + 2;
        }

        private String call(NestBytecodeDemo owner) {
            return owner.label();
        }
    }

    private class Inner {
        private int read() {
            return secret + 1;
        }
    }

    public static void main(String[] args) {
        NestBytecodeDemo outer = new NestBytecodeDemo();
        Probe probe = new Probe();

        System.out.println("private-field=" + probe.read(outer));
        System.out.println("private-method=" + probe.call(outer));
        System.out.println("inner=" + outer.new Inner().read());

        System.out.println("host="
                + (Probe.class.getNestHost()
                        == NestBytecodeDemo.class));
        System.out.println("nestmate="
                + Probe.class.isNestmateOf(Inner.class));
        System.out.println("same-package-nestmate="
                + Probe.class.isNestmateOf(Neighbor.class));
        System.out.println("contains-inner="
                + Arrays.asList(
                        NestBytecodeDemo.class.getNestMembers())
                        .contains(Inner.class));
    }
}

class Neighbor {
}
```

**Giải thích source:**

1. `NestBytecodeDemo` có field `private int secret` và method `private String label()`.
2. `Probe` là **static nested class** với hai method private; nó đọc `owner.secret` và gọi `owner.label()`, đều là private của lớp ngoài.
3. `Inner` là **non-static inner class**, giữ một liên hệ đến outer instance và đọc `secret`.
4. Ngược lại, `main` ở outer gọi các method `private` của `Probe`/`Inner`. Đây là ví dụ truy cập **hai chiều giữa các classfile cùng nest**.
5. `Neighbor` là lớp **top-level độc lập** trong cùng default package (vì cùng file không có `package`), nên **không** là nestmate của `Probe`. Việc nó nằm cùng source file không khiến chúng chung nest.
6. `getNestHost`, `isNestmateOf`, `getNestMembers` là API `java.lang.Class` xuất hiện từ Java 11.

Trong code production, nên khai báo package rõ ràng; default package được dùng ở đây **chỉ để giảm số bước cấu hình và dễ đọc classfile**.

## 6. Biên dịch, chạy và kiểm tra classfile version

Đứng tại thư mục chứa file, chạy:

```bash
javac --release 11 -encoding UTF-8 NestBytecodeDemo.java
java NestBytecodeDemo
```

**Đầu ra chương trình, theo đúng mã mẫu:**

```text
private-field=42
private-method=ready
inner=41
host=true
nestmate=true
same-package-nestmate=false
contains-inner=true
```

Đầu ra này đã được đối chiếu trên OpenJDK khi biên dịch với `--release 11`. Nó không phụ thuộc thứ tự `getNestMembers()` vì chương trình chỉ hỏi danh sách có chứa `Inner.class` hay không.

Ý nghĩa:

- `private-field=42`: `Probe.read` truy cập trực tiếp field private có giá trị 40, cộng 2.
- `private-method=ready`: `Probe.call` gọi được method `private label()` của host.
- `inner=41`: `Inner.read` đọc private field của outer instance, cộng 1.
- `host=true`: host của `Probe` là `NestBytecodeDemo`.
- `nestmate=true`: `Probe` và `Inner` có chung nest host.
- `same-package-nestmate=false`: `Neighbor` vẫn là lớp top-level độc lập.
- `contains-inner=true`: host liệt kê/nhận diện `Inner` qua API runtime.

**Vì sao dùng `--release 11`?** Tham số này chọn API và target bytecode phù hợp Java 11 khi dùng JDK hỗ trợ release đó. Nếu chỉ chạy `javac NestBytecodeDemo.java` trên một JDK mới hơn, classfile có thể có **major version khác 55**. Không thể dùng việc source “trông giống Java 11” để khẳng định classfile đang chạy trên JVM 11.

Kiểm tra version:

```bash
javap -v NestBytecodeDemo
```

Trong phần đầu của output nên thấy:

```text
  minor version: 0
  major version: 55
```

**55.0 là classfile version của Java 11.** Các số constant-pool index, mã flags khác, thứ tự một số attributes và debug metadata có thể khác giữa các compiler/JDK; **đừng so toàn bộ `javap -v` bằng một chuỗi output cố định**. Chỉ kiểm những đặc trưng cần thiết.

## 7. Đọc `NestMembers` tại lớp host

Chạy:

```bash
javap -v NestBytecodeDemo
```

Ở gần cuối kết quả, tìm:

```text
NestMembers:
  NestBytecodeDemo$Inner
  NestBytecodeDemo$Probe
```

Đây là **trích đoạn minh họa từ bản biên dịch mẫu**, không phải toàn bộ output. Thứ tự `Inner` và `Probe` có thể thay đổi tùy compiler. Điều quan trọng là host **liệt kê cả hai member**.

**Không chờ thấy `NestHost: class NestBytecodeDemo` trên chính host.** Nest host thể hiện việc nó là host bằng `NestMembers`, không cần tự chỉ tới chính nó bằng `NestHost`.

### 7.1. Khối `NestMembers` nói gì?

Với classfile `NestBytecodeDemo.class`:

- `NestMembers` chứa tên nhị phân các lớp `NestBytecodeDemo$Inner` và `NestBytecodeDemo$Probe` mà host cho phép.
- Host mặc nhiên là thành viên của nest do nó đứng đầu.
- Phần nội dung này là **metadata classfile** để JVM xét quyền truy cập `private`.
- Metadata này không biến private thành package-private hoặc public. Chỉ các nestmates hợp lệ có quyền tương ứng.

`Class.getNestMembers()` ở runtime trả về **array các `Class<?>`** của nest, không phải các dòng text, và có thể phải tải/xác minh class. Thứ tự thành viên sau host **không được bảo đảm**, vì vậy không assert `members[1]` phải là `Probe.class`.

### 7.2. Nếu không thấy `NestMembers`?

Đừng vội cho rằng `javap` hỏng. Có thể:

- Bạn đang xem **classfile khác** do đường dẫn/classpath trỏ nhầm.
- Mã được biên dịch cho một target bytecode **không chứa nest attributes**.
- Class là **member**, vì vậy nó có `NestHost` thay vì `NestMembers`.
- Class là **một nest singleton**, không có thành viên cần liệt kê.
- Một tool xử lý bytecode/JAR đã biến đổi hoặc loại mất metadata.
- Code đã đổi, lớp lồng không còn được tạo trong lần build hiện tại.

Kiểm tra đúng tên lớp, đúng bản output, đúng classfile version và toàn bộ đường đóng gói rồi mới kết luận.

## 8. Đọc `NestHost` tại member

Để xem classfile của static nested class:

```bash
javap -v 'NestBytecodeDemo$Probe'
```

Output rút gọn (phần attribute):

```text
NestHost: class NestBytecodeDemo
```

Tương tự:

```bash
javap -v 'NestBytecodeDemo$Inner'
```

Bạn cũng sẽ tìm được `NestHost: class NestBytecodeDemo`.

### 8.1. Quy tắc quote tên có dấu `$`

Dấu `$` trong tên nhị phân rất quan trọng:

- **Bash/Zsh**: dùng `'NestBytecodeDemo$Probe'` để shell không giải thích `$Probe` là biến môi trường.
- **PowerShell**: dùng **single quotes** như trên để không nội suy biến `$Probe`.
- **Windows CMD**: dùng **double quotes**: `javap -v "NestBytecodeDemo$Probe"`.
- Hoặc truyền đường dẫn file `.class` phù hợp và chắc chắn đúng classpath, tránh để shell xử lý `$` theo tên lớp.

Không phải tên lớp Java source `NestBytecodeDemo.Probe`. Với class đã biên dịch, tên nhị phân dùng `NestBytecodeDemo$Probe`; nếu có package `com.example` thì dùng `'com.example.NestBytecodeDemo$Probe'` với `-cp` phù hợp.

### 8.2. Điều gì tạo nên quan hệ nest hợp lệ?

Không đủ chỉ đọc một bên:

```text
NestBytecodeDemo.class
  NestMembers: [NestBytecodeDemo$Probe, NestBytecodeDemo$Inner]

NestBytecodeDemo$Probe.class
  NestHost: NestBytecodeDemo

NestBytecodeDemo$Inner.class
  NestHost: NestBytecodeDemo
```

Đây là **mô tả logic** theo hai phía, không phải nguyên output. JVM còn xét điều kiện **cùng runtime package**, gồm package và class loader định nghĩa tương thích. Một class khác không được tự gắn `NestHost` trỏ tới lớp nạn nhân rồi giành quyền `private` nếu host không cho phép và runtime package không hợp lệ.

**Không nhầm cùng tên package với cùng nest:** `Neighbor` trong demo nằm ở cùng default package, nhưng `isNestmateOf` trả `false`.

## 9. Disassemble `Probe`: đọc field private trực tiếp

Lệnh quan trọng nhất của bài:

```bash
javap -c -p 'NestBytecodeDemo$Probe'
```

Ví dụ output của method `read` từ bản biên dịch thử:

```text
  private int read(NestBytecodeDemo);
    Code:
       0: aload_1
       1: getfield      #7                  // Field NestBytecodeDemo.secret:I
       4: iconst_2
       5: iadd
       6: ireturn
```

Phân tích từng lệnh:

| Lệnh | Ý nghĩa |
| --- | --- |
| `aload_1` | Đưa argument `owner` (biến local index 1) lên operand stack |
| `getfield NestBytecodeDemo.secret:I` | Đọc trực tiếp field instance `private int secret` từ outer object |
| `iconst_2` | Đưa hằng số 2 lên stack |
| `iadd` | Cộng hai giá trị `int` |
| `ireturn` | Trả kết quả `int` |

**Dấu hiệu chính:** lệnh là **`getfield` trỏ thẳng tới `NestBytecodeDemo.secret`**, không gọi qua một phương thức trung gian do compiler sinh ra.

Trong dòng `Field NestBytecodeDemo.secret:I`, `I` là JVM field descriptor của `int`. Các số như `#7` là **index của constant pool**, có thể khác theo compiler/JDK, không phải một phần bất biến của API. Đừng hardcode `#7` vào automated tests.

### 9.1. Vì sao `private` vẫn được phép?

Ở bytecode, JVM cần kiểm tra quyền truy cập vào field được tham chiếu. `Probe` và `NestBytecodeDemo` là nestmates hợp lệ (theo attributes), nên `getfield` này được phép. Một lớp top-level `Neighbor` không thuộc nest không thể tự dùng `getfield` để vượt `private`; nếu classfile bị tạo thủ công và truy cập sai, JVM sẽ từ chối trong cơ chế linkage/access check.

**Không thể suy ra từ bytecode rằng mọi code trong package đều có quyền private.** JVM thực thi điều kiện nest, không chỉ tên package.

### 9.2. Không tìm nhầm `access$...`

Với demo biên dịch target Java 11, việc đọc field private qua nestmates không đòi hỏi compiler sinh một `access$...` bridge. Bạn có thể rà nhanh danh sách method:

```bash
javap -p NestBytecodeDemo
javap -p 'NestBytecodeDemo$Probe'
```

Trong ví dụ này **không có synthetic bridge `access$...` chỉ để đọc `secret`**. Nhưng tuyệt đối **không viết quy tắc “mọi classfile Java 11 đều không có synthetic method”**: compiler vẫn có thể phát sinh synthetic members cho các tính năng khác, hoặc thư viện biến đổi bytecode có thể tạo chúng.

**Special Note về kiến thức hiện hành:** trọng tâm ở đây là cách `javac` Java 11+ phát classfile và cách JVM hiện nay kiểm tra nest. Các workaround từ thời target JVM cũ chỉ nên được biết như bối cảnh lịch sử, **không** phải kỹ thuật nên triển khai cho mã mới.

## 10. Disassemble `Probe`: gọi private method

Trong cùng output:

```text
  private java.lang.String call(NestBytecodeDemo);
    Code:
       0: aload_1
       1: invokevirtual #13                 // Method NestBytecodeDemo.label:()Ljava/lang/String;
       4: areturn
```

Quan sát: `Probe.call` dùng **`invokevirtual` trỏ tới phương thức private `NestBytecodeDemo.label()`**. Theo JEP 181, cách gọi private method của **nestmate** có thể dùng `invokevirtual` (và các trường hợp phù hợp với `invokeinterface`) thay vì nhất thiết dựa trên `invokespecial` của phương thức do class hiện tại khai báo.

Diễn giải:

- `aload_1`: load tham số `owner`.
- `invokevirtual NestBytecodeDemo.label:()Ljava/lang/String;`: gọi method tên `label`, descriptor không có argument và trả `String`.
- `areturn`: trả object reference từ method `call`.

**Lưu ý về opcode:** lựa chọn chính xác của `javac` cho những trường hợp phức tạp có thể phụ thuộc loại method/call site. Không ghi quy tắc “mọi lời gọi private đều dùng `invokevirtual`”. Điều cần kiểm tra là **tham chiếu trực tiếp** và **quy tắc nest access của JVM**, đồng thời nhận diện opcode thực trong output đang nghiên cứu.

Dòng `#13` là constant-pool index, không nên so cứng. Cùng source có thể tạo constant pool khác khi thêm một dòng log hoặc thay đổi bản JDK.

## 11. Disassemble non-static inner class và hiểu `this$0`

Chạy:

```bash
javap -c -p 'NestBytecodeDemo$Inner'
```

Trong bản biên dịch kiểm thử, bạn có thể thấy một field:

```text
  final NestBytecodeDemo this$0;
```

Và trong method `read()`:

```text
  private int read();
    Code:
       0: aload_0
       1: getfield      #1                  // Field this$0:LNestBytecodeDemo;
       4: getfield      #13                 // Field NestBytecodeDemo.secret:I
       7: iconst_1
       8: iadd
       9: ireturn
```

**Ý nghĩa:**

- `Inner` là lớp **không static**, cần tham chiếu outer instance để truy cập field `secret`. `javac` có thể sinh field `this$0` cho quan hệ này.
- Lệnh `getfield this$0` lấy outer object.
- Lệnh `getfield NestBytecodeDemo.secret:I` sau đó **đọc trực tiếp private field** từ outer object.
- `this$0` không phải một `access$...` accessor method. Đây là **field giữ reference**, phục vụ ngữ nghĩa inner instance.
- `NestHost`/`NestMembers` giải thích **quyền truy cập private**, không phải cách Java lưu object reference ở inner class.

Vì vậy, không nên đọc dòng `this$0` rồi kết luận JEP 181 không được dùng; hãy kiểm tra riêng **attributes** và **lệnh truy cập private**.

## 12. Phân biệt `InnerClasses`, `EnclosingMethod` và nest attributes

`javap -v` thường in nhiều thuộc tính gần nhau. Chúng có vai trò khác nhau:

| Attribute | Ý nghĩa chính | Có quyết định private nest access không? |
| --- | --- | --- |
| `InnerClasses` | Mô tả tên và cấu trúc nested/member classes theo classfile | **Không**, tự nó chưa đủ |
| `EnclosingMethod` | Chỉ ra ngữ cảnh bao quanh cho local/anonymous class khi thích hợp | **Không**, không thay thế nest authorization |
| `NestHost` | Member ghi nhận nest host mà nó thuộc về | **Có**, cùng các kiểm tra cần thiết |
| `NestMembers` | Host liệt kê các member được phép thuộc nest | **Có**, cùng điều kiện runtime package |
| `SourceFile` | Tên file source phục vụ debug | **Không** |
| `LineNumberTable` | Ánh xạ bytecode tới dòng source | **Không** |
| `Synthetic`/`ACC_SYNTHETIC` | Đánh dấu thành viên nhân tạo theo compiler/VM | **Không** phải bằng chứng quyền nest |

Với source có local hoặc anonymous classes, `javac` cũng có thể ghi nest metadata thích hợp. Tuy nhiên không đoán quan hệ nest chỉ từ tên `$1` hoặc `$2Local`; kiểm tra chính file `.class` bằng `javap -v` và dùng `Class.isNestmateOf` nếu cần xác thực runtime.

**Không dùng `getDeclaringClass()` thay `getNestHost()`:** một API mô tả quan hệ lexical/declaration, API kia mô tả **nest của JVM**. Một lớp thuộc một nest có thể nằm ở nhiều mức lexical nesting; chúng không phải một khái niệm tương đương trong mọi trường hợp.

## 13. Kiểm chứng runtime bằng reflection trong Java 11

Ngoài `javap`, JDK 11 thêm các API trực tiếp trên `java.lang.Class`:

| API | Kết quả | Dùng khi |
| --- | --- | --- |
| `clazz.getNestHost()` | `Class<?>` là host đã xác định | So host của member |
| `clazz.getNestMembers()` | Mảng `Class<?>[]` gồm các thành viên nest | Kiểm tra membership khi runtime |
| `a.isNestmateOf(b)` | Boolean hai lớp có cùng nest | Assertion an toàn |
| `clazz.getDeclaringClass()` | Lớp khai báo lexical khi có | **Không** thay thế nest check |

Trong demo đã chạy:

```java
Probe.class.getNestHost() == NestBytecodeDemo.class
Probe.class.isNestmateOf(Inner.class)
Probe.class.isNestmateOf(Neighbor.class)
Arrays.asList(NestBytecodeDemo.class.getNestMembers())
        .contains(Inner.class)
```

Tương ứng `true`, `true`, `false`, `true`. Đoạn trên là **trích đoạn biểu thức** được trích từ chương trình đầy đủ, không tự in kết quả nếu đặt riêng.

### 13.1. `getNestMembers()` trả theo thứ tự nào?

Theo Java 11 API:

- Phần tử đầu tiên là **nest host**.
- Các member phía sau **không có thứ tự được bảo đảm**.
- Các loại lỗi linkage/class loading có thể được biểu lộ khi runtime cố xác minh member.
- Một class bình thường không có metadata nest vẫn có một **singleton nest** của chính nó.

Đừng viết test `getNestMembers()[1] == Probe.class`. Viết test membership với `contains` hoặc tập hợp tên thích hợp (tránh trùng tên do classloader khác).

### 13.2. `javap` và reflection có thể khác nhau vì sao?

`javap` xem **classfile trên đĩa** mà bạn chỉ định; reflection nói về **`Class` đã tải thật vào JVM**. Có thể không giống nhau nếu:

- JVM đang tải JAR cũ trong classpath thay vì file bạn vừa compile.
- Java agent hoặc framework thực hiện **bytecode transformation** khi load.
- Hai classloader tải các định nghĩa trùng tên nhưng không cùng runtime package.
- Bạn kiểm tra file đã chỉnh sửa nhưng tiến trình Java chưa khởi động lại.
- Ứng dụng sử dụng multi-release JAR và runtime chọn classfile entry khác.
- Một member không thể được tải/xác minh ở runtime mặc dù `javap` đọc được metadata của nó.

Vì vậy, kết quả “javap thấy NestHost” là **bằng chứng metadata tĩnh**, không phải bằng chứng mọi đường truy cập private sẽ hoạt động trong ứng dụng đã chạy.

## 14. Bài kiểm thử tự động bằng `javap`

Trong CI, mục tiêu là kiểm tra **bất biến**, không so toàn bộ output `javap` từng byte. Các thao tác cơ bản:

### 14.1. Bash/Linux/macOS

Sau khi biên dịch:

```bash
javac --release 11 -encoding UTF-8 NestBytecodeDemo.java

javap -v NestBytecodeDemo | grep -E 'major version:|NestMembers:'
javap -v 'NestBytecodeDemo$Probe' | grep -E 'major version:|NestHost:'
javap -c -p 'NestBytecodeDemo$Probe' | grep -E 'getfield|invokevirtual'
```

Các dòng lọc chứng minh:

- Host có `major version: 55` và `NestMembers:`.
- Member có `major version: 55` và `NestHost: class NestBytecodeDemo`.
- Method private của member có **`getfield`** và **`invokevirtual`** truy cập trực tiếp các private members đúng tên.

**Giới hạn:** `grep` chỉ tìm text; nó không xác nhận quan hệ host–member có tương thích toàn bộ khi runtime. Để CI quyết định PASS/FAIL đáng tin cậy, kiểm tra cả **giá trị** (host name, member names, version, method owner) và chạy test `Class.isNestmateOf`. Nếu dùng script với `set -e`, hãy tách nhánh xử lý no-match để trả lỗi đủ nghĩa.

### 14.2. PowerShell trên Windows

```powershell
javac --release 11 -encoding UTF-8 NestBytecodeDemo.java

javap -v NestBytecodeDemo |
    Select-String 'major version:|NestMembers:'

javap -v 'NestBytecodeDemo$Probe' |
    Select-String 'major version:|NestHost:'

javap -c -p 'NestBytecodeDemo$Probe' |
    Select-String 'getfield|invokevirtual'
```

Trong PowerShell dùng **single quotes** cho tên có `$`. Với **CMD**, có thể dùng:

```bat
javap -v "NestBytecodeDemo$Probe"
javap -c -p "NestBytecodeDemo$Probe"
```

Không đưa ```bash``` commands vào PowerShell như một loại script chạy nguyên trạng nếu có toán tử/quote khác nhau; chọn cú pháp đúng môi trường. Các lệnh trên chỉ **xem** file; không sửa classfile.

### 14.3. Script kiểm tra không dựa vào constant-pool index

Nếu viết test tự động, **đừng** assert một dòng có `#7` hoặc `#13` vì constant pool index thay đổi. Thay vào đó:

1. Tìm `major version: 55` của classfile target 11.
2. Tìm khối `NestMembers` và đúng tên member ở host.
3. Tìm `NestHost: class NestBytecodeDemo` ở classfile member.
4. Tìm `Field NestBytecodeDemo.secret:I` trong body `read` và `Method NestBytecodeDemo.label:()Ljava/lang/String;` trong `call`.
5. Chạy `java NestBytecodeDemo` và assert các dòng Boolean.
6. Nếu packaging/toolchain có thể đổi classfiles, **lặp lại trên artifact sau cùng**, không chỉ output compile trước đóng gói.

Đừng sử dụng việc “không thấy `access$...`” làm **điều kiện duy nhất**: class khác có thể dùng synthetic cho lý do khác. Đúng hơn là kiểm tra metadata nest và truy cập private trực tiếp của chính code bạn cần.

## 15. Chẩn đoán lỗi khi kết quả không như mong đợi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `major version` không phải 55 | Không build target Java 11 | Compile lại với `--release 11`, kiểm tra file thực đang xem |
| `NestMembers` vắng ở outer | Nhầm class, source khác, compiler/target khác, metadata đã bị xóa | Xác nhận file/classpath và rebuild đúng |
| `NestHost` vắng ở member | Nhầm member hoặc classfile bị đổi | Chọn đúng tên nhị phân và kiểm tra attributes |
| Lệnh `javap` không tìm thấy `NestBytecodeDemo$Probe` | Shell nội suy `$Probe` hoặc classpath không đúng | Dùng single quotes Bash/PowerShell, CMD double quotes |
| Không thấy `private read()` | Không dùng `-p` hoặc nhầm class | Chạy `javap -c -p` |
| Trông giống đã gọi accessor | Xem nhầm class/target hoặc code đã qua transform | Soạn đúng target 11, inspect output mới |
| Thấy `this$0` rồi tưởng private access bị gián tiếp | Đây là outer-reference của non-static inner | Xem tiếp lệnh `getfield` tới private field |
| `isNestmateOf` false dù cùng package | Package name không quyết định nest | Kiểm tra cả `NestHost`, `NestMembers`, loader |
| Runtime `NoClassDefFoundError` hoặc linkage error | Thiếu host/member, class path, loader khác, metadata lệch | Bảo toàn classfiles host và members, kiểm tra artifact cuối |
| `IllegalAccessError`/`IncompatibleClassChangeError` trong đường private access | Có thể classfile nest không nhất quán hoặc phiên bản bị trộn | Điều tra đúng phiên bản classfile và điều kiện runtime package |
| `getNestMembers()` lỗi khi load một member | Thành viên liệt kê bị thiếu hoặc không xác minh được | Đảm bảo packaging và loading nhất quán |
| `javap` cho kết quả khác runtime | JVM load bản khác hoặc agent transform | So đường dẫn JAR, classloader, deployment thật |
| Multi-release JAR cho kết quả lạ | `javap` bằng classpath không tự chọn version như runtime MRJAR | Kiểm tra đúng classfile entry thực được runtime dùng |
| Build chạy JDK mới nhưng triển khai JDK 11 lỗi | Target/API không khớp hoặc JAR lẫn class mới | Build `--release 11`, kiểm tra mọi dependency classfile |

**Không giả định một loại exception duy nhất cho mọi metadata sai.** JVM có thể phát sinh lỗi tại bước loading, linking hoặc khi first access thực sự xảy ra, tùy điều kiện. Dùng stack trace và classpath để điều tra mà không “vá” bằng cách nâng visibility `private` lên `public`.

## 16. Khi đóng gói thư viện, obfuscation và bytecode instrumentation

Trong ứng dụng thực, classfile không phải lúc nào cũng từ `javac` đi thẳng tới JVM. Nó có thể đi qua:

- Tool đóng gói hoặc làm gọn JAR.
- Obfuscator/renamer.
- Bytecode transformer trong build.
- Code coverage instrumentation.
- Java agent tạo/chỉnh sửa class.
- Module/JAR shading và relocation.

**Quy tắc cốt lõi:** nếu một tool đổi tên hoặc di chuyển `NestBytecodeDemo$Probe`, nó phải cập nhật quan hệ **`NestHost`/`NestMembers`** và metadata khác phù hợp. Nếu loại bỏ outer host vì “chẳng có ai gọi tới class ngoài”, nestmates còn lại có thể không xác định được host hợp lệ khi thực thi private access.

Một lỗi thực tế được tài liệu release Java 11 cảnh báo: **nest host classfile có thể vẫn cần tồn tại tại runtime** dù code chỉ chủ động dùng nested class. Đừng xóa nó dựa trên phân tích dependency quá đơn giản.

### 16.1. Kiểm tra artifact sau đóng gói

Thực hành cho pipeline:

1. Compile target Java 11.
2. Đảm bảo JAR chứa host và member classfiles thích hợp.
3. Inspect **đúng artifact đã qua obfuscation/transform** bằng `javap -v` cho host và member.
4. Kiểm tra method private thật bằng `javap -c -p`.
5. Chạy integration test trên artifact đó và một runtime tương thích với classfile.
6. Quan sát các lỗi linkage, classloader, module/package và đường private access.

Nếu dùng multi-release JAR, tài liệu `javap` Java 11 lưu ý công cụ **không tự hiểu multirelease JAR** theo cách runtime chọn entry khi dùng classpath thông thường. Cần xác định đúng entry (ví dụ base so với `META-INF/versions/...`) rồi inspect classfile mong muốn; không lấy một lần `javap -cp app.jar` làm bằng chứng cho mọi runtime version.

## 17. Quy tắc runtime package và bảo vệ private

JVM không chỉ kiểm tên host:

- Một member có thể khai báo `NestHost` trỏ tới host.
- Host phải **liệt kê và cho phép** member qua `NestMembers`.
- Hai bên phải ở cùng **runtime package** phù hợp (bao gồm package và defining class loader).
- Các điều kiện về format và loading/linking phải được đáp ứng.
- Nếu host không chỉ định `NestMembers` hoặc không nhận member, việc chỉ có một `NestHost` ở member là không đủ.

Đây là cơ chế JVM kiểm soát `private`. Nó không cấp khả năng phản chiếu tùy ý tới mọi package, không thay các quy tắc module/open package cho reflection sâu từ bên ngoài và **không** biến `Neighbor` thành nestmate.

### 17.1. Nest là quan hệ runtime, không phải một annotation tùy chọn

Không có annotation `@NestHost` để gắn vào source là xong. `javac` phát các **classfile attributes** theo cấu trúc lexical và phiên bản target. Bytecode library hoặc agent muốn tạo/sửa lớp phải hiểu đặc tả classfile, kiểm tra tương thích và cập nhật hợp lệ.

Đừng tự chỉnh file `.class` bằng hex editor hay xóa một attribute để thử “đổi quyền truy cập” trên chương trình production. Nếu muốn nghiên cứu lỗi bảo vệ, chỉ làm trong môi trường test cô lập với dữ liệu giả và classfile tự tạo.

### 17.2. Lỗi đóng gói và khả năng tải host

Nếu JVM cần host để kiểm tra `private` mà host không có trong artifact, kết quả có thể là lỗi lúc load/link/access, không phải “JVM bỏ qua nest và cho private access theo tên”. Đây là lý do bài kiểm tra `javap` và runtime test nên đi cùng nhau.

## 18. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Cùng package là cùng nest” | **Sai.** Hai top-level class cùng package vẫn có nest riêng |
| “Tên lớp có `$` là chứng cứ đủ” | **Sai.** Tên nhị phân không tự cấp quyền |
| “`InnerClasses` thay cho `NestHost`” | **Sai.** Có mục đích metadata khác |
| “Host cũng cần `NestHost` trỏ đến chính nó” | **Sai.** Host dùng `NestMembers`, bản thân host mặc nhiên thuộc nest |
| “Chỉ cần member khai báo host là đủ” | **Sai.** Host phải chấp thuận và runtime package hợp lệ |
| “`getNestMembers` có thứ tự cố định” | **Sai.** Trừ host đầu tiên, thứ tự không đảm bảo |
| “Private method luôn phải dùng `invokespecial`” | **Sai.** Nestmates có thể gọi direct, ví dụ mẫu dùng `invokevirtual` |
| “Từ Java 11 không bao giờ còn synthetic” | **Sai.** `this$0` và synthetic cho mục đích khác vẫn có thể tồn tại |
| “`javap` chạy và kiểm tra runtime access hộ tôi” | **Sai.** Nó phân tích classfile tĩnh |
| “`-v` và `-c` giống nhau” | **Sai.** Một bên cấu trúc/attributes, một bên lệnh bytecode |
| “`javap` hiện mọi private dù không dùng `-p`” | **Không nên giả định.** Dùng `-p` để chắc chắn hiển thị private methods |
| “Thêm visibility public là cách sửa LinkageError” | **Sai hướng.** Điều tra classfile host/member và loader |
| “Lấy `javap -cp JAR` là đủ cho mọi multi-release runtime” | **Không.** Cần inspect đúng entry đang được chọn |
| “Chỉ cần test source, không cần test JAR sau transform” | **Không.** Công cụ có thể làm mất metadata nest |

## 19. Bài luyện tập và đáp án

**Bài 1.** Bạn biên dịch `NestBytecodeDemo.java` với `--release 11`. `javap -v NestBytecodeDemo` nên có dấu hiệu gì?

**Đáp án:** `major version: 55` và khối `NestMembers` chứa member classfiles, trong ví dụ gồm `NestBytecodeDemo$Probe` và `NestBytecodeDemo$Inner`. Thứ tự không cần cố định.

**Bài 2.** Với `javap -v 'NestBytecodeDemo$Probe'`, cần tìm gì?

**Đáp án:** Thuộc tính `NestHost: class NestBytecodeDemo`. Member không nên bị kỳ vọng có `NestMembers` giống host.

**Bài 3.** Bạn muốn chứng minh `Probe.read` đọc private `secret` trực tiếp. Dùng lệnh nào?

**Đáp án:** `javap -c -p 'NestBytecodeDemo$Probe'`; xem `private int read(...)` có `getfield` trỏ tới `NestBytecodeDemo.secret:I`. Không dựa vào constant pool index `#7`.

**Bài 4.** Vì sao `Neighbor.class` trong cùng file source vẫn không là nestmate của `Probe.class`?

**Đáp án:** `Neighbor` là top-level class độc lập, không được khai báo nested trong `NestBytecodeDemo`. Nest access phụ thuộc metadata hợp lệ và runtime package, **không** phụ thuộc file source/package đơn thuần.

**Bài 5.** `javap -p 'NestBytecodeDemo$Inner'` in `this$0`. Điều này có nghĩa Java 11 không hỗ trợ direct private access?

**Đáp án:** Không. `this$0` lưu outer instance cho non-static inner. Truy cập `private secret` vẫn có thể là `getfield` trực tiếp như demo.

**Bài 6.** CI assert `getNestMembers()[1] == Probe.class` nhưng đôi khi thất bại. Lỗi ở đâu?

**Đáp án:** Thứ tự các member sau host không được bảo đảm. Kiểm tra membership bằng `contains` hoặc set; không phụ thuộc index của member.

**Bài 7.** `javap -v` thấy `NestHost` nhưng khi chạy JAR bị `IllegalAccessError`. Có phải `javap` sai?

**Đáp án:** Không nhất thiết. `javap` chỉ đọc tĩnh. Có thể host không liệt kê member, classfile khác được load, classloader/runtime package sai hoặc artifact đã bị đổi. Kiểm tra cả host/member trên artifact cuối cùng và chạy test runtime.

**Bài 8.** Tại sao `javac --release 11` quan trọng khi biên dịch trên JDK mới?

**Đáp án:** Giúp target đúng classfile/API Java 11; `javap -v` khi đó phải phản ánh major version 55. Không nhầm bytecode đời mới với lớp Java 11 chỉ vì cú pháp source tương tự.

**Bài 9.** Chỉ thấy `InnerClasses` ở classfile có đủ chứng minh có nest-based private access?

**Đáp án:** Không. Cần `NestHost/NestMembers` và kiểm tra runtime tương ứng. `InnerClasses` là metadata lexical, không tự cấp quyền nest.

**Bài 10.** Một obfuscator đổi tên `Probe` nhưng không cập nhật danh sách trên host. Có nguy cơ gì?

**Đáp án:** Nest metadata không nhất quán; access check có thể không nhận class là nestmate, gây linkage/access error. Tool phải cập nhật attributes và pipeline phải test artifact sau biến đổi.

## 20. Checklist kiểm tra trong dự án thật

Trước khi kết luận kết quả disassemble đáng tin:

1. **Đúng file:** đã xác minh source và classfile thuộc đúng build/module, không phải bản cũ?
2. **Đúng target:** `javac --release 11` và `javap -v` cho `major version: 55` nếu deploy Java 11?
3. **Đúng host:** `NestMembers` nằm trên host, chứa những member cần thiết?
4. **Đúng member:** mỗi nested class cần access có `NestHost` trỏ tới host?
5. **Đúng quan hệ:** hai phía nhất quán, cùng runtime package/loader?
6. **Đúng bytecode:** `javap -c -p` cho thấy private field/method access thực, không chỉ lời suy đoán từ Java source?
7. **Không nhầm synthetic:** phân biệt `this$0` với private access bridge?
8. **Runtime reflection:** `getNestHost`/`isNestmateOf` cho kết quả mong đợi?
9. **Đúng artifact cuối:** sau shading, obfuscation, instrumentation hoặc đóng gói JAR, attributes vẫn hợp lệ?
10. **Không tự phá access:** giữ `private` khi cần; không nâng thành public để tránh lỗi linker?
11. **Multi-release:** có xem đúng class entry tương ứng với runtime đang dùng?
12. **Tự động hóa:** assert bất biến (version, attributes, method owner), không assert constant-pool indexes/order không được bảo đảm?

**Ghi nhớ:** `javap -v` cho thấy **quan hệ nest ở classfile**; `javap -c -p` cho thấy **lệnh truy cập private**; `Class.getNestHost()/isNestmateOf()` là đối chứng **khi chạy thật**. Đọc cả ba góc độ trước khi kết luận một lỗi liên quan nest-based access.

## 21. Tài liệu chính thức còn áp dụng

- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): mục tiêu, thiết kế nest và tích hợp `javac`/JVM, giới thiệu từ Java 11.
- [Oracle Java SE 11 — `javap`](https://docs.oracle.com/en/java/javase/11/tools/javap.html): `-v`, `-c`, `-p`, `-cp`, cấu trúc output và các giới hạn khi xem JAR.
- [Oracle Java SE 11 — `Class`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getNestHost`, `getNestMembers` và `isNestmateOf` (có từ Java 11).
- [Java Virtual Machine Specification SE 11 — `4.7.28 NestHost`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28): định nghĩa attribute host.
- [Java Virtual Machine Specification SE 11 — `4.7.29 NestMembers`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29): danh sách member do host chấp nhận.
- [Java Virtual Machine Specification SE 11 — `5.4.4 Access Control`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4): runtime nestmate private access, điều kiện xác minh.
- [Oracle Java 11 Release Notes — Nest-Based Access Control](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): trình bày thay đổi `javac`/JVM và lưu ý phải giữ nest host classfile.
- [Oracle Java SE 25 — `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): các API nest vẫn được hỗ trợ trên JDK hiện đại.

**Lời khuyên thực hành:** luôn kiểm tra **chính file `.class` sẽ được chạy**, không chỉ một bản demo hoặc một build trước đóng gói. Khi xử lý lỗi, giữ nguyên định nghĩa `private` và sửa nguyên nhân classfile/classpath/nest metadata.
