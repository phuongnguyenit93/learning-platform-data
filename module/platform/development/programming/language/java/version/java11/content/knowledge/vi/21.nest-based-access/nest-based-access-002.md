# Truy cập private giữa các lớp trong cùng nest (Java 11)

**Nest-based access control** là thay đổi ở **Java Virtual Machine (JVM)** được đưa vào **Java 11** qua **JEP 181**. Một lớp top-level và những lớp/interface lồng bên trong nó thường được biên dịch thành nhiều tệp `.class` riêng, nhưng vẫn là các phần của **cùng một đơn vị mã nguồn**. Java 11 cho phép JVM nhận biết chúng thuộc **cùng một nest** và cho phép những lớp đó truy cập trực tiếp các thành viên `private` của nhau.

Ví dụ hợp lệ:

```java
public class Vault {
    private String code = "secret";

    static class Reader {
        String read(Vault vault) {
            return vault.code; // Hợp lệ: Reader thuộc cùng nest với Vault.
        }
    }
}
```

Đây chỉ là **đoạn mã minh họa**, không có `main`. Cú pháp truy cập này **đã hợp lệ ở cấp ngôn ngữ Java trước Java 11**. Điểm mới của Java 11 là **cách JVM thực thi quyền truy cập**: compiler có thể phát sinh bytecode gọi thẳng tới thành viên `private`, thay vì thêm một phương thức `synthetic` có mức truy cập rộng hơn để làm cầu nối.

**Điều quan trọng cần nhớ:** *private giữa các nestmate* **không phải** *private giữa mọi lớp ở cùng package* và **không** phải cơ chế bỏ qua Java module security. Một lớp top-level khác, dù nằm trong cùng file `.java` hay cùng package, không đương nhiên thuộc nest này.

Bài thuộc nhóm **Nest-based access** của Java 11. Các khái niệm, class-file attributes, phương thức phản chiếu và quy tắc JVM ở đây vẫn có ý nghĩa trong các JDK hiện đại. Khi thực hành, nên dùng JDK đang được nhà cung cấp hỗ trợ và biên dịch bằng `javac --release 11` để tương thích Java 11, thay vì phụ thuộc một runtime cũ không còn nhận cập nhật bảo mật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khái niệm **nest host**, **nest member** và **nestmate**.
2. Phân biệt quy tắc `private` ở **Java source code** với quy tắc kiểm tra quyền ở **JVM bytecode**.
3. Viết ví dụ lớp ngoài, static nested class, non-static inner class và các lớp lồng có thể gọi `private` của nhau.
4. Biết vì sao **Java 8 thường dùng synthetic accessor** còn compiler nhắm Java 11 có thể dùng **truy cập trực tiếp**.
5. Đọc các class-file attributes `NestHost` và `NestMembers` bằng `javap -v`.
6. Dùng `Class.getNestHost()`, `Class.getNestMembers()` và `Class.isNestmateOf(...)` để quan sát cấu trúc nest.
7. Hiểu các trường hợp **không thuộc cùng nest**: hai lớp top-level cùng file/package, kế thừa, hoặc tên class có dấu `$` tự đặt.
8. Biết giới hạn liên quan **runtime package**, class loader, module, reflection và `MethodHandles.Lookup`.
9. Chẩn đoán lỗi khi trộn bytecode cũ/mới hoặc cấu hình build/class loader không đồng nhất.
10. Kiểm chứng chương trình Java 11, bytecode và reflection bằng những bài thử có stdout rõ ràng.

## 2. Một nest là gì?

Một **nest** là nhóm lớp/interface mà JVM cho phép chia sẻ quyền truy cập **`private`**. Trong mô hình biên dịch Java thông thường, một lớp top-level là **nest host**, còn các lớp/interface khai báo lồng trực tiếp hoặc gián tiếp trong đó là **nest members**.

Ví dụ:

```text
Source: Store.java
   |
   +-- public class Store              (nest host)
       |
       +-- static class Reader         (nest member)
       +-- static class Writer         (nest member)
       +-- class Inner                 (nest member)
       +-- interface Validator         (nest member)

Compiler Java 11 có thể tạo:
   Store.class
   Store$Reader.class
   Store$Writer.class
   Store$Inner.class
   Store$Validator.class
```

Những class file này là **những lớp JVM riêng biệt**, nhưng JVM biết chúng thuộc cùng một nest khi metadata hợp lệ. Vì vậy, `Store$Reader` có thể truy cập trường `private` của `Store` và của `Store$Writer` nếu cú pháp Java nguồn cho phép.

### Ba khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Nest host** | Lớp/interface đại diện cho nest | `Store` |
| **Nest member** | Lớp/interface ghi nhận host của mình | `Store$Reader` |
| **Nestmates** | Hai lớp/interface có **cùng nest host** | `Store$Reader` và `Store$Writer` |

Một lớp thông thường không tham gia nest nhiều thành viên vẫn **thuộc một nest gồm chính nó**. Vì thế mọi class đều có một nest host, kể cả một lớp top-level không có lớp lồng.

**Không phải quan hệ kế thừa.** Nestmate không yêu cầu `extends` hoặc `implements` lẫn nhau. Ngược lại, subclass không tự có quyền đọc `private` của superclass chỉ vì kế thừa. Nest là **quan hệ truy cập nội bộ** của các loại được biên dịch chung trong một cấu trúc hợp lệ.

### Vì sao cần nest nếu Java đã cho lớp lồng đọc private?

Java source vốn cho phép các phần lồng nhau của một khai báo truy cập thành viên `private` phù hợp. Nhưng trước Java 11, JVM thường áp `private` theo **lớp đã khai báo thành viên**, trong khi mỗi lớp lồng là một `.class` riêng. Compiler phải thêm một cách truy cập trung gian để giữ đúng ngữ nghĩa Java source.

JEP 181 đưa JVM lại gần mô hình mà lập trình viên Java đã hiểu từ lâu: **các thành viên của cùng nest được xem như một đơn vị truy cập private**. Thay đổi xảy ra chủ yếu ở **class file format**, **linker/access checks** và **compiler output**, chứ không thêm một từ khóa Java mới.

## 3. Trước và sau Java 11: synthetic accessor và truy cập trực tiếp

Giả sử:

```java
public class Box {
    private int number = 17;

    static class Reader {
        int read(Box box) {
            return box.number;
        }
    }
}
```

Đây là **source fragment hợp lệ**, không có `main`.

### Khi biên dịch hướng tới Java 8

Compiler cần duy trì quyền `private` ở Java source, nhưng JVM với mô hình cũ không có nestmate metadata. Nó thường sinh một phương thức hỗ trợ dạng:

```java
// Minh họa ý nghĩa bytecode do compiler sinh, KHÔNG phải
// mã nguồn cần tự viết.
static int access$000(Box box) {
    return box.number;
}
```

Tên thực tế và số thứ tự `access$...` do compiler quyết định. Phương thức **synthetic accessor** này có quyền gọi tới `private` do nó nằm trong chính class sở hữu member. Lớp `Reader` thay vì truy cập field trực tiếp sẽ gọi accessor đó.

Đây là giải pháp lịch sử để giữ tương thích Java language, nhưng có hạn chế:

- Tạo thêm member trong class file.
- Accessor thường có **package-private access ở bytecode**, mở rộng bề mặt truy cập trong runtime package so với ý định `private` trong source.
- Có thêm phương thức trung gian và metadata cần compiler/runtime quản lý.
- Khi phân tích stack trace/bytecode có thể thấy những method không tồn tại trong source.

**Không phải mọi phương thức synthetic đều là accessor lịch sử của nest.** Java compiler còn dùng synthetic members cho các tính năng khác. Java 11 chỉ **giải quyết các accessor cần thiết cho private access giữa nestmates**, không xóa sạch mọi member có cờ `ACC_SYNTHETIC`.

### Khi biên dịch hướng tới Java 11

Compiler có thể ghi metadata nest vào các file `.class`, cho JVM hiểu `Box` và `Box$Reader` là nestmates. Bytecode của `Reader.read` được phép truy cập trực tiếp `Box.number`; **không cần tạo `access$000` chỉ để đọc field đó**.

```text
Java source
     |
     +---- javac --release 8 ----> class file version 52.0
     |                           + synthetic accessors (khi cần)
     |
     +---- javac --release 11 ---> class file version 55.0
                                 + NestMembers/NestHost
                                 + private access trực tiếp
```

Chú ý: `--release 8` ở đây dùng để **so sánh lịch sử bytecode**, **không phải khuyến nghị chạy runtime Java 8 trong production**. Dùng JDK còn được hỗ trợ để biên dịch và phân tích. Với code cần dùng `Class.getNestHost()` hoặc `isNestmateOf()`, phải biên dịch ở mức Java **11 trở lên** vì các API đó không tồn tại trong Java 8.

## 4. Ví dụ 1 — lớp ngoài, hai static nested class và inner class đọc private của nhau

Đây là chương trình độc lập minh họa cả **truy cập từ trong ra ngoài**, **giữa hai lớp lồng ngang hàng**, **từ ngoài vào lớp lồng**, và **trong non-static inner class**.

Tạo file **`NestmateAccessDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public final class NestmateAccessDemo {
    private final String ownerSecret = "owner-secret";
    private final int value = 11;

    private String ownerMethod() {
        return "private-method";
    }

    static final class Reader {
        private final String readerSecret = "reader-secret";

        private String readOwner(NestmateAccessDemo owner) {
            return owner.ownerSecret + " / " + owner.ownerMethod();
        }

        private String readWriter(Writer writer) {
            return writer.writerSecret;
        }
    }

    static final class Writer {
        private final String writerSecret = "writer-secret";

        private String readReader(Reader reader) {
            return reader.readerSecret;
        }
    }

    private final class Inner {
        private int sumWithOne() {
            return value + 1;
        }
    }

    public static void main(String[] args) {
        NestmateAccessDemo owner = new NestmateAccessDemo();
        Reader reader = new Reader();
        Writer writer = new Writer();

        System.out.println("Reader -> outer: " + reader.readOwner(owner));
        System.out.println("Reader -> writer: " + reader.readWriter(writer));
        System.out.println("Writer -> reader: " + writer.readReader(reader));
        System.out.println("Outer -> reader: " + reader.readerSecret);
        System.out.println("Inner -> outer: " + owner.new Inner().sumWithOne());

        System.out.println("Reader host: " +
                Reader.class.getNestHost().getSimpleName());
        System.out.println("Reader/Writer nestmates: " +
                Reader.class.isNestmateOf(Writer.class));
        System.out.println("Reader/OtherTopLevel nestmates: " +
                Reader.class.isNestmateOf(OtherTopLevel.class));
        System.out.println("OtherTopLevel host: " +
                OtherTopLevel.class.getNestHost().getSimpleName());

        String members = Arrays.stream(
                        NestmateAccessDemo.class.getNestMembers())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println("Nest members: " + members);
    }
}

final class OtherTopLevel {
}
```

### Biên dịch và chạy

Dùng JDK hiện hành còn được hỗ trợ, có compiler hỗ trợ `--release 11`:

```sh
javac --release 11 -encoding UTF-8 NestmateAccessDemo.java
java NestmateAccessDemo
```

**Stdout chính xác:**

```text
Reader -> outer: owner-secret / private-method
Reader -> writer: writer-secret
Writer -> reader: reader-secret
Outer -> reader: reader-secret
Inner -> outer: 12
Reader host: NestmateAccessDemo
Reader/Writer nestmates: true
Reader/OtherTopLevel nestmates: false
OtherTopLevel host: OtherTopLevel
Nest members: Inner, NestmateAccessDemo, Reader, Writer
```

### Giải thích những quyền truy cập đã diễn ra

**Dòng 1 — Reader → Outer:** `Reader.readOwner` đọc `owner.ownerSecret` và gọi `owner.ownerMethod()`, cả hai đều `private` trong `NestmateAccessDemo`. Vì lớp Reader được lồng trong host, Java source chấp nhận và JVM Java 11 có thể cho truy cập trực tiếp.

**Dòng 2 — Reader → Writer:** `Reader.readWriter` đọc `writer.writerSecret`, dù trường này `private` và được khai báo trong **lớp lồng ngang hàng**, không phải trong Outer. Hai lớp có **cùng nest host**.

**Dòng 3 — Writer → Reader:** quyền truy cập có tính hai chiều trong phạm vi các khai báo nguồn hợp lệ: `Writer` cũng đọc `Reader.readerSecret`. Điều này không cần hai class kế thừa nhau.

**Dòng 4 — Outer → Reader:** class ngoài `NestmateAccessDemo` đọc trường `private` của `Reader`. Không cần thêm getter chỉ để giao tiếp giữa những phần của cùng một cấu trúc lồng.

**Dòng 5 — Inner → Outer:** `Inner` là **non-static inner class**, có một instance `NestmateAccessDemo` bao quanh. Nó đọc `value` và trả `12`. Quyền private giữa nestmates **khác** với việc inner class giữ tham chiếu tới outer instance; đây là hai cơ chế liên quan nhưng không đồng nghĩa.

**Dòng 6–7 — runtime metadata:** `Reader.class.getNestHost()` trả host; `Reader.class.isNestmateOf(Writer.class)` là `true` vì có chung host.

**Dòng 8–9 — một lớp top-level khác:** `OtherTopLevel` đặt trong **cùng file `.java`** nhưng không được khai báo *bên trong* `NestmateAccessDemo`, nên là **một nest độc lập**. `isNestmateOf` trả `false`.

**Dòng 10 — member listing:** chúng ta **sort** theo `getSimpleName()` để kết quả ổn định. Thứ tự những nest members sau host theo đặc tả `Class.getNestMembers()` không được bảo đảm, nên **đừng phụ thuộc thứ tự array trả về** khi viết test.

### Static nested và non-static inner khác gì?

| Thuộc tính | `static class Reader` | `class Inner` |
| --- | --- | --- |
| Có instance outer bao quanh theo cấu trúc Java? | Không tự động | Có |
| Có thể tạo trực tiếp khi không có outer object? | Có | Thường cần outer instance |
| Có thể là nestmate với outer? | Có | Có |
| Có thể truy cập `private static` của outer? | Có, theo Java source rules | Có |
| Có thể truy cập `private instance` của outer? | Có nếu có **một đối tượng outer để tham chiếu** | Có thể tham chiếu outer instance bao quanh |
| Có phải subclass outer? | Không | Không |

**Nest membership không tự tạo ra một outer object.** Một static nested class muốn đọc `private instance` của outer vẫn cần một reference tới đối tượng ấy, ví dụ tham số `owner` ở chương trình trên.

### Private constructor cũng nằm trong quyền nest

Nestmate access của JVM không chỉ bao gồm fields và methods, mà còn bao gồm **private constructors**. Ví dụ source fragment đặt bên trong một class host:

```java
static final class Token {
    private final int value;

    private Token(int value) {
        this.value = value;
    }
}

static final class TokenFactory {
    static Token create() {
        return new Token(7); // Hợp lệ trong cùng nest.
    }
}
```

Đây là **đoạn mã lồng trong class ngoài**, không phải chương trình `main` độc lập. Nó không làm constructor `private` trở thành public đối với một lớp top-level bên ngoài.

## 5. Ba phương thức phản chiếu nest mới từ Java 11

API `java.lang.Class` có ba phương thức trọng tâm:

| API | Kết quả | Dùng khi nào |
| --- | --- | --- |
| `getNestHost()` | `Class<?>` đại diện host của nest | Xác định một class thuộc nest nào |
| `getNestMembers()` | `Class<?>[]` chứa host và các members | Quan sát metadata nest, test cấu trúc |
| `isNestmateOf(Class<?> other)` | `boolean` | Kiểm tra hai classes có cùng nest host |

Cả ba có từ **Java 11**. Không tìm chúng trong Java 8 class library và không dùng chúng với source target `--release 8`.

### `getNestHost()`

`Reader.class.getNestHost()` trong chương trình trên trả `NestmateAccessDemo.class`. `OtherTopLevel.class.getNestHost()` trả **chính `OtherTopLevel.class`** vì đó là nest đơn thành viên.

Với các class không tham gia nest nhiều thành viên, **host chính là class đó**. Các type đại diện primitive, array và `void` cũng được phản chiếu như nest đơn thành viên theo đặc tả Java 11.

### `isNestmateOf`

Hai `Class` là nestmates nếu có chung nest host. Một class là nestmate **với chính nó**. Nhưng:

- Cùng package **không đủ**.
- Cùng class loader **không đủ**.
- Cùng module **không đủ**.
- Hai class cùng interface hoặc cùng superclass **không đủ**.
- Có cùng chuỗi ký tự trước dấu `$` trong tên file **không đủ**.

### `getNestMembers()` và thứ tự

`getNestMembers()` của Java 11 trả host làm phần tử đầu, sau đó liệt kê các thành viên khác **theo thứ tự không xác định**. Tài liệu còn cho phép duplicate entries trong kết quả theo các điều kiện đặc tả; vì thế production code không nên dùng index cụ thể để đoán `Reader` là phần tử số 1 và `Writer` là phần tử số 2.

Khi cần so sánh trong unit test, nên chuyển về tập định danh class hoặc sort trước khi kiểm tra. Không nên coi thứ tự do một JDK phát ra là một hợp đồng ổn định giữa các phiên bản/compiler.

### Không dùng metadata như cơ chế cấp quyền

Các lời gọi trên **chỉ quan sát** quan hệ nest hiện có. Không có API Java chuẩn dạng `joinNest(...)` cho một class tùy ý. Không thể tự gọi `getNestHost()` rồi “đăng ký” một class không liên quan để đọc private của class khác.

## 6. Ví dụ 2 — bytecode Java 8 và Java 11 khác nhau thế nào?

Để quan sát trực tiếp tác dụng của JEP 181, dùng một source file **không sử dụng API chỉ có từ Java 11**. Nhờ vậy có thể biên dịch hai lần với `--release 8` và `--release 11` bằng cùng một JDK hỗ trợ cả hai target.

Tạo file **`NestBytecodeProbe.java`**:

```java
public final class NestBytecodeProbe {
    private final int secret = 41;

    private int privateMethod() {
        return secret + 1;
    }

    static final class Accessor {
        int read(NestBytecodeProbe owner) {
            return owner.secret + owner.privateMethod();
        }
    }

    public static void main(String[] args) {
        System.out.println("Private field + method: " +
                new Accessor().read(new NestBytecodeProbe()));
    }
}
```

Biên dịch ở mức Java 11:

```sh
javac --release 11 -encoding UTF-8 NestBytecodeProbe.java
java NestBytecodeProbe
```

**Stdout:**

```text
Private field + method: 83
```

Tại sao là 83? `secret = 41` và `privateMethod() = 42`, nên `41 + 42 = 83`.

### So sánh class files bằng `javap`

Chạy trong thư mục có source file và Java tools. Trên shell hỗ trợ lệnh `mkdir`:

```sh
mkdir -p bytecode8 bytecode11
javac --release 8 -d bytecode8 NestBytecodeProbe.java
javac --release 11 -d bytecode11 NestBytecodeProbe.java

javap -p -classpath bytecode8 NestBytecodeProbe
javap -p -classpath bytecode11 NestBytecodeProbe

javap -v -classpath bytecode11 NestBytecodeProbe
javap -v -classpath bytecode11 'NestBytecodeProbe$Accessor'

javap -c -p -classpath bytecode8 'NestBytecodeProbe$Accessor'
javap -c -p -classpath bytecode11 'NestBytecodeProbe$Accessor'
```

Dấu `'...'` quanh tên lớp có `$` tránh shell diễn giải `$Accessor` thành biến. Trên Windows, PowerShell cũng chấp nhận chuỗi đơn nháy cho tham số class name; lệnh `mkdir -p` có thể cần thay bằng `New-Item -ItemType Directory -Force ...`. Một số JDK hiện đại cảnh báo rằng `--release 8` cũ/obsolete; đây chỉ là thao tác phân tích sự khác nhau về class files.

**Các điểm có thể xác minh từ output, không phụ thuộc số thứ tự accessor:**

| Kiểm tra | Khi target Java 8 | Khi target Java 11 |
| --- | --- | --- |
| Class file version | `52.0` | `55.0` |
| Synthetic accessor phục vụ truy cập private từ nested class | Có thể thấy `access$...` | Không cần accessor đó |
| `NestMembers` trong host | Không có | Có |
| `NestHost` trong `Accessor.class` | Không có | Có |
| Bytecode access private | Có thể gọi method cầu nối | Có thể truy cập member trực tiếp |
| Output chương trình | `83` | `83` |

Số tên `access$000`, `access$100`, thứ tự methods, constant pool indices và biểu diễn `javap` có thể khác theo compiler. **Đừng viết test chỉ dựa vào một số định danh accessor cố định.**

**Thực nghiệm bytecode:** hai target tạo **cùng kết quả chương trình**, nhưng file class khác. Khi target 11, host ghi `NestMembers` và nested class ghi `NestHost`, nên không cần dùng bridge để thực hiện quyền private cho ví dụ.

### Không phụ thuộc runtime Java 8 trong production

Phần so sánh `--release 8` có mục đích giải thích **vì sao JEP 181 tồn tại**, không nhằm bảo vệ một kiểu biên dịch cũ hay khuyến nghị runtime hết hỗ trợ. Các dự án mới nên dùng JDK được bảo trì, đồng thời chọn `--release` theo contract tương thích thực tế của sản phẩm.

## 7. Hai class-file attributes mới: `NestHost` và `NestMembers`

JEP 181 cập nhật định dạng class file của JVM. Trong Java 11 (class-file version `55.0`), metadata nest thể hiện chủ yếu qua:

| Attribute | Nơi thường xuất hiện | Ý nghĩa |
| --- | --- | --- |
| **`NestMembers`** | Trên **nest host** | Host liệt kê tên các class/interface thuộc nest |
| **`NestHost`** | Trên **nest member** | Member khai báo nest host của nó |

Ví dụ từ `NestBytecodeProbe`:

```text
NestBytecodeProbe.class
    NestMembers:
        NestBytecodeProbe$Accessor

NestBytecodeProbe$Accessor.class
    NestHost: class NestBytecodeProbe
```

Đây là **minh họa các thông tin cần tìm trong `javap -v`**, không phải cam kết bản dump byte-for-byte giống nhau giữa JDK khác nhau. Class file còn có các attributes khác như `InnerClasses` và, với các lớp local/anonymous, `EnclosingMethod`; **chúng không thay thế `NestHost`/`NestMembers` khi JVM cần xác định nest-based private access**.

### Phải có xác nhận hai chiều

Không đủ để một class tự ghi rằng host của nó là một class nổi tiếng khác:

1. Member khai báo host qua `NestHost`.
2. Host liệt kê member qua `NestMembers`.
3. JVM xác minh quan hệ phù hợp, bao gồm ràng buộc **cùng runtime package**.
4. Nếu quan hệ hợp lệ, hai class có thể cùng tham gia kiểm tra private access.

Một bytecode generator không thể chiếm quyền đọc private của một thư viện chỉ bằng cách tạo class có tên giống hoặc viết bừa một `NestHost`. Nest membership được JVM kiểm chứng; không phải danh sách “bạn bè” do một class không tin cậy tự khai báo đơn phương.

### Package và class loader có vai trò gì?

Một **runtime package** không chỉ là chuỗi ký tự `package com.example`. Trong mô hình JVM, lớp tải bởi các class loader khác nhau có thể là các định danh/runtime package khác nhau, dù source package name giống nhau. Nest members phải thỏa ràng buộc package/runtime của JVM; không cho một plugin do loader độc lập tự tham gia nest của class ứng dụng chỉ qua tên.

Với modules, các ràng buộc module/class loader và package ownership vẫn áp dụng. Nest không phải cửa sau vượt module encapsulation.

### Nếu metadata nest sai hoặc không nhất quán?

Ví dụ host không liệt kê member, member chỉ sai host, một class file bị thiếu, hoặc có loader conflict. Tùy thời điểm resolution và **phiên bản JDK**, có thể thấy `IllegalAccessError` hoặc lỗi linkage/validation khác; phương thức `getNestMembers()` cũng có hành vi kiểm tra thay đổi qua các bản JDK.

**Đừng phụ thuộc một loại exception duy nhất để thiết kế flow nghiệp vụ.** Java 15 đã điều chỉnh cách JVM xử lý những nest metadata hỏng để nhất quán hơn: class có quan hệ nest không hợp lệ có thể được coi như **self-hosted** và quyền private vẫn bị từ chối. Khi gặp lỗi, hãy kiểm tra build/class loader/class files, không tự làm suy yếu `private`.

## 8. Local class và anonymous class cũng có thể là nestmates

Một nest không chỉ bao gồm `static class` và `inner class` có tên. Compiler Java 11 cũng có thể đưa **local class** và **anonymous class** vào cùng nest của cấu trúc ngoài.

Tạo chương trình độc lập **`LocalNestDemo.java`**:

```java
public class LocalNestDemo {
    private final int secret = 7;

    void show() {
        class Local {
            private int doubled() {
                return secret * 2;
            }
        }
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("Anonymous reads: " + secret);
            }
        };
        System.out.println("Local reads: " + new Local().doubled());
        System.out.println("Local nest host: " +
                Local.class.getNestHost().getSimpleName());
        System.out.println("Anonymous nestmate: " +
                anonymous.getClass().isNestmateOf(LocalNestDemo.class));
        anonymous.run();
    }

    public static void main(String[] args) {
        new LocalNestDemo().show();
    }
}
```

Biên dịch/chạy:

```sh
javac --release 11 -encoding UTF-8 LocalNestDemo.java
java LocalNestDemo
```

**Stdout chính xác:**

```text
Local reads: 14
Local nest host: LocalNestDemo
Anonymous nestmate: true
Anonymous reads: 7
```

**Giải thích:** local class `Local` và anonymous class được tạo trong `show()` truy cập field `private secret` của host. Cả hai class đều có thể có metadata liên kết với nest host `LocalNestDemo`. Số thứ tự trong tên file sinh ra như `$1` hay `$2` **không** phải API ổn định; đừng dựa vào nó để tìm class hoặc cấp quyền.

**Lưu ý về lambda:** biểu thức lambda thường được triển khai bằng cơ chế khác (ví dụ `invokedynamic` và runtime-generated implementation). Không tự suy luận rằng mỗi lambda luôn tạo một class-file có tên cố định và `NestHost` giống local/anonymous class. Nếu đang phân tích lambda, hãy xem công cụ/JDK thực tế và không dựa vào tên triển khai sinh ra.

## 9. Ví dụ 3 — reflection có kiểm tra access trong và ngoài nest

Cơ chế nest-based access cũng liên quan đến **core reflection**. Java 11 cho phép quyền private được xét theo quan hệ nest của **caller** và class sở hữu member; một caller cùng nest có thể truy cập private member phản chiếu mà không cần cố mở access thủ công. Nhưng caller **ngoài nest** không được phép chỉ vì cùng source file.

Tạo file **`ReflectionNestDemo.java`**:

```java
import java.lang.reflect.Field;

public class ReflectionNestDemo {
    private static final class Item {
        private final String secret = "visible-to-nest";
    }

    public static void main(String[] args) throws Exception {
        Item item = new Item();
        Field field = Item.class.getDeclaredField("secret");
        System.out.println("Same-nest reflective read: " + field.get(item));
        System.out.println("Other-top-level reflective read: " +
                Outsider.tryRead(field, item));
        System.out.println("Host: " + Item.class.getNestHost().getSimpleName());
    }
}

final class Outsider {
    static String tryRead(Field field, Object target) throws Exception {
        try {
            return (String) field.get(target);
        } catch (IllegalAccessException expected) {
            return "denied";
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 ReflectionNestDemo.java
java ReflectionNestDemo
```

**Stdout chính xác:**

```text
Same-nest reflective read: visible-to-nest
Other-top-level reflective read: denied
Host: ReflectionNestDemo
```

Tại sao?

- `ReflectionNestDemo.main` là caller nằm trong cùng nest với `Item`. Quyền truy cập `private` được chấp thuận khi `Field.get` kiểm tra.
- `Outsider.tryRead` là một **phương thức được khai báo ở top-level class khác**; đó là caller thật của `Field.get`. Vì `Outsider` không thuộc nest của `Item`, quyền private mặc định bị từ chối bằng `IllegalAccessException`.
- Chương trình **không hề gọi `setAccessible(true)`**. Mục tiêu là chứng minh quyền private của nestmate, không mô phỏng cách bypass encapsulation.

### `setAccessible` và module không phải là nest access

Reflection có các cơ chế như `AccessibleObject.setAccessible(...)` và `trySetAccessible()`. Đây là **cơ chế khác**, chịu quy tắc kiểm soát truy cập và module opens. Đừng hiểu JEP 181 là “tự động cho mọi class reflect mọi private field”:

- Caller là nestmate hợp lệ có thể được quyền private theo quy tắc JVM.
- Caller không phải nestmate vẫn bị kiểm tra quyền.
- Việc yêu cầu suppress access checks cho caller khác phụ thuộc module encapsulation, quyền truy cập và các điều kiện liên quan.
- Một package có thể cần được `opens` phù hợp cho deep reflection từ module khác; **`exports` không đồng nghĩa `opens`**.
- Không thêm `--add-opens` bừa bãi như một cách sửa việc phân chia lớp sai thiết kế.

Đối với code thường, hãy giữ truy cập `private` trực tiếp **trong đúng phạm vi Java source** và dùng API public/package-private có chủ đích cho giao tiếp ngoài nest. Reflection nên dành cho framework/tooling khi có lý do rõ ràng.

## 10. Cùng package, cùng file, cùng module vẫn chưa đủ

Đây là các tình huống nên phân biệt:

| Quan hệ | Có tự thành nestmate không? | Giải thích |
| --- | --- | --- |
| Outer và static nested class trong nó | Thường có (khi compiler tạo metadata hợp lệ) | Cùng cấu trúc lồng |
| Hai static nested class cùng outer | Thường có | Cùng nest host |
| Outer và non-static inner class | Thường có | Cùng cấu trúc lồng và đúng runtime metadata |
| Local/anonymous class bên trong outer | Có thể có, như demo | Compiler đưa vào nest |
| Hai top-level class cùng file `.java` | **Không** | Khai báo top-level riêng |
| Hai top-level class cùng package | **Không** | Package-level access không phải nest-private |
| Subclass trong package khác | **Không** | Kế thừa không cho private access |
| Hai class cùng module | **Không** | Module membership không tạo nest |
| Một class được đặt tên `Outer$Fake` | **Không** | Tên class không thay thế attributes/validation |
| Class cùng tên/package nhưng loader khác | **Không đủ** | Runtime identity và access constraints |
| Class chỉ có `NestHost` tự khai báo nhưng host không chấp thuận | **Không** | Cần metadata/validation hợp lệ |

### Ví dụ không hợp lệ ở Java source

```java
class Account {
    private int pin = 1234;
}

class Auditor {
    int read(Account account) {
        return account.pin; // COMPILE ERROR: pin has private access.
    }
}
```

Đây là **phản ví dụ cố ý gây compile error**, không phải chương trình hoàn chỉnh để chạy. `Account` và `Auditor` là hai **top-level classes**; đặt trong cùng file hoặc cùng package cũng không làm `Auditor` thành nestmate. Không sửa bằng cách biến `pin` thành `public` nếu không thật sự có yêu cầu công khai dữ liệu.

Nếu cần cung cấp chức năng hợp lệ, hãy định nghĩa API có chủ đích (ví dụ phương thức xác minh PIN thay vì lộ PIN), phù hợp nguyên tắc least privilege. **Nest không phải lý do tăng visibility của member.**

## 11. Tương tác với inheritance, interface và constructor

### `private` không phải `protected`

Một subclass có thể dùng những member được phép theo `public`/`protected`/package-private rules; nó **không tự đọc `private`** của superclass. Điều này không thay đổi trong Java 11. Nếu subclass đồng thời là một nestmate do quan hệ lồng hợp lệ, quyền nó có là **vì nest**, không phải vì `extends`.

### Nested interface và loại nested

Java source có thể khai báo interface lồng trong class/interface; compiler có thể cho chúng cùng nest, với những member private mà ngôn ngữ cho phép. Trong Java 11, interface có thể có `private` methods (từ Java 9) để chia sẻ logic giữa default/static methods trong chính interface. Nest-based access của JVM còn áp dụng cho **classes và interfaces** phù hợp.

Không cần ghi `NestHost`/`NestMembers` bằng Java source; `javac` tạo class-file metadata.

### Private constructor trong nest

Khi factory và target class là nestmates theo một cấu trúc nguồn hợp lệ, factory có thể gọi **private constructor** của target. Nhưng `private` không tự cấp phép subclass bên ngoài gọi constructor đó bằng `super(...)`. Đừng nhầm nestmate access với quy tắc kế thừa.

## 12. MethodHandles.Lookup và quyền truy cập private

JEP 181 cũng ảnh hưởng tới các kiểm tra quyền cấp JVM có liên quan đến **method handles**. `java.lang.invoke.MethodHandles.Lookup` thể hiện các quyền truy cập của caller, và một lookup có đủ quyền `PRIVATE` trong ngữ cảnh phù hợp có thể truy cập thành viên private của nestmate theo các quy tắc hiện hành.

Một số API thường gặp:

| API | Vai trò |
| --- | --- |
| `MethodHandles.lookup()` | Tạo lookup mang quyền của caller |
| `lookup.findGetter(...)` | Tìm field getter method handle theo access modes |
| `lookup.findVirtual(...)` | Tìm method handle cho instance method theo quyền được phép |
| `MethodHandles.privateLookupIn(...)` | Xin private lookup trong target class **khi điều kiện quyền và module cho phép** |
| `lookup.lookupModes()` | Quan sát quyền hiện có của lookup |

**Không suy luận chỉ từ `isNestmateOf(...) == true` rằng mọi method handle lookup được tạo ở bất cứ caller nào đều có đủ `PRIVATE` quyền.** Điều kiện caller, access modes, module relations, class loader và cách tạo/biến đổi lookup vẫn quan trọng.

`privateLookupIn` cũng **không** là cách tùy ý sửa thiếu nest metadata hoặc vượt module boundaries. Với named modules, deep access có thể yêu cầu target package được opened đúng điều kiện. Kiểm tra lỗi `IllegalAccessException` và sửa thiết kế module/API, không tự động mở toàn bộ package chứa secret.

### Có cần đổi source thành MethodHandles để “dùng nest” không?

**Không.** Với Java source thông thường, compiler và JVM xử lý nestmates phía dưới. Chỉ dùng `MethodHandles` khi ứng dụng/framework thật sự cần dynamic invocation hay hiệu năng của một cơ chế chuyên biệt. Viết code kiểu:

```java
return owner.ownerSecret;
```

bên trong một nested class được phép sẽ rõ ràng hơn một chuỗi reflective lookup chỉ để truy cập cùng field.

## 13. Tương thích bytecode và các lần nâng cấp JDK

Một vấn đề thực tế khi nâng cấp Java là **không phải thay source là xong**. Các bản build có thể dùng nhiều compiler target và phân phối class files tới runtime khác nhau.

### Quy tắc tương thích cơ bản

- Class files target **Java 11** dùng format version **55.0** và có thể chứa `NestHost`/`NestMembers`; yêu cầu JVM **Java 11 trở lên** để load.
- Class files target **Java 8** dùng version **52.0**; khi javac cần vượt hạn chế private theo bytecode cũ, nó có thể sinh synthetic accessors.
- **Chạy file version 52.0 trên JDK mới không tự nâng cấp nó thành version 55.0**, cũng không tự thêm nest metadata.
- Nếu cần hỗ trợ JVM cũ hơn Java 11, không biên dịch production artifacts thành Java 11 class files. Thay vào đó, chọn target tương thích theo **platform support policy**.
- Không copy một class file mới trong khi giữ class file cũ của cùng cấu trúc lồng một cách tùy tiện: metadata nest có thể không đồng bộ.

### Rủi ro build một nửa

Ví dụ bạn biên dịch lại `Outer$Inner.class` với target Java 11 nhưng giữ `Outer.class` cũ không có `NestMembers`. Bytecode mới có thể cố truy cập `Outer.privateField` trực tiếp trong khi JVM không xác nhận quan hệ nest hợp lệ. Kết quả có thể là linkage/access failure.

Các nguyên nhân hay gặp:

1. Build cache stale.
2. Chỉ thay một tệp `.class` bên trong JAR.
3. Multi-release JAR có class files tương ứng release bị đặt sai vị trí.
4. Java agent/bytecode transformer loại hoặc sửa metadata nest.
5. Shading/obfuscation đổi tên class nhưng không cập nhật `NestHost`/`NestMembers` nhất quán.
6. Custom class loader tải nested class và host dưới những runtime identities không tương thích.
7. Công cụ bytecode rất cũ chưa hiểu các attributes mới của class version 55.

**Cách sửa đúng:** clean rebuild toàn bộ nhóm nested classes bằng toolchain được hỗ trợ; cập nhật bytecode transformer, packager, agent hoặc obfuscator; dùng `javap -v` kiểm tra host/member attributes; chạy integration tests trong runtime thực tế. **Không** sửa bằng cách biến mọi field thành `public`.

### Lưu ý hành vi lỗi khác nhau giữa JDK release

Các JDK sau Java 11 đã điều chỉnh một số chi tiết kiểm tra metadata nest không hợp lệ. Vì vậy, một lỗi kiểu `IllegalAccessError` hoặc `LinkageError` khi bytecode hỏng không nhất thiết có cùng thông báo/loại cụ thể giữa Java 11 và JDK hiện đại. Điều **không thay đổi** là private access không được tự cấp khi quan hệ nest không hợp lệ.

Không viết business code dựa trên một string exception message từ JVM. Hãy tìm lỗi build hoặc class loader ở gốc.

## 14. Tác động đến encapsulation và thiết kế API

Nest-based access **giữ** ý nghĩa của `private` trong thiết kế source, thay vì buộc compiler tạo những accessor package-private để mô phỏng nó.

### Lợi ích

- Giảm nhu cầu tạo **compiler-generated synthetic accessors** cho private access giữa các nested classes.
- JVM trực tiếp nhận biết một đơn vị code có quan hệ lồng nhau.
- Tăng độ nhất quán giữa source-level intent và bytecode-level access control.
- Có metadata rõ cho compiler, reflective APIs và tooling.
- Giúp phân tích bytecode của một cấu trúc class lớn chính xác hơn.

**Không hứa một mức tăng tốc độ cụ thể.** JIT có thể đã inline những synthetic accessors lịch sử. Cần benchmark workload thực tế trước khi khẳng định hiệu năng tăng; tác dụng quan trọng ở đây là **mô hình access control đúng và bytecode gọn về ý định**.

### Nest lớn có thể trở thành vùng tin cậy quá rộng

Tất cả những nested classes trong cùng nest có thể dùng private access ở cấp JVM trong giới hạn quy tắc source. Vì vậy, khi đặt một helper vào trong class chứa secret, hãy xem helper là **một phần của cùng đơn vị triển khai được tin cậy**.

- Không nhét plugin/extension không tin cậy vào cùng cấu trúc nested chỉ để tiện gọi private field.
- Không lưu secret ở một field private rồi cho rằng mọi nested helper tự động là ranh giới bảo mật riêng biệt.
- Nếu hai thành phần không nên biết cấu trúc nội bộ của nhau, cân nhắc tách thành top-level classes và đưa ra **API tối thiểu** có kiểm soát.
- Dùng access modifier theo ý định: `private` cho chi tiết nội bộ; `package-private` cho API nội package có chủ đích; `public` cho hợp đồng công khai.
- Không dùng reflection/bytecode tricks để thay thế một API rõ ràng giữa các module.

Private là **cơ chế giới hạn truy cập của ngôn ngữ và JVM**, không phải giải pháp bảo vệ dữ liệu ở runtime chống mọi tác nhân chạy trong tiến trình có quyền. Với data secrets, còn cần bảo mật bộ nhớ, process boundary, key management và authorization.

## 15. Những lỗi thường gặp

| Lỗi hiểu/triển khai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Java 11 mới cho inner class đọc private outer” | Source Java đã cho phép nhiều trường hợp từ trước | Nêu chính xác: JVM **được thêm nest access**, javac bỏ nhu cầu bridge |
| “Cùng file `.java` là cùng nest” | Hai top-level declarations khác nest | Đọc cấu trúc lồng và `getNestHost()` |
| “Cùng package là nestmate” | Package-private và nest-private khác nhau | Kiểm tra `isNestmateOf` |
| “Subclass đọc private của superclass” | Kế thừa không đổi `private` thành `protected` | Dùng API theo thiết kế |
| “JVM Java 11 không còn synthetic methods” | Synthetic còn nhiều mục đích khác | Chỉ kỳ vọng giảm accessor cho nest private |
| “NestMembers có thứ tự ổn định” | Member order không được bảo đảm | Sort hoặc so set khi test |
| “Tên có `$` nghĩa là nested” | Tên không đủ chứng minh metadata/nguồn | Quan sát `NestHost`/`NestMembers` và bytecode |
| “Một class tự khai báo NestHost là đủ” | Host cũng phải chấp nhận member, cùng runtime package | Dùng compiler/metadata hợp lệ |
| “Class file target 8 chạy trên JDK 25 tự thành nestmate bytecode” | JVM không thêm attributes vào file cũ | Recompile target 11+ khi phù hợp |
| “Chỉ copy Inner.class mới lên server” | Host và member metadata có thể lệch | Clean rebuild/redeploy toàn bộ nhóm |
| “`getNestMembers()[1]` chắc chắn là Reader” | Không có bảo đảm thứ tự member | Tìm theo `Class<?>`, không theo index |
| “`getNestHost` tự cấp quyền” | Metadata API chỉ đọc | Không dùng như bypass |
| “Nested class static tự có outer instance” | `static` không giữ instance outer tự động | Truyền reference hợp lệ |
| “Dùng `setAccessible(true)` để sửa mọi lỗi private” | Có thể vượt ranh giới thiết kế và bị module từ chối | Sửa cấu trúc/API và chỉ reflection có lý do |
| “Java 11 nest cho phép truy cập private giữa module tùy ý” | Vẫn có runtime package/module constraints | Tuân thủ module boundaries |
| “`javap -v` có private access thì ai cũng có thể gọi” | Bytecode access được JVM kiểm tra theo caller/nest | Phân biệt nestmates và classes ngoài |
| “Cứ thấy `IllegalAccessError` thì tăng visibility lên public” | Có thể do class files hoặc class loader không nhất quán | Kiểm tra build/attrs trước khi sửa API |
| “Java 11 bắt buộc đổi mọi lớp lồng” | Không có cú pháp source bắt buộc mới | Chỉ cập nhật toolchain/tests nếu cần |

## 16. Các bài kiểm thử nên có khi nâng cấp dự án

| Test | Điều cần xác nhận |
| --- | --- |
| Outer đọc private field nested class | Biên dịch và chạy hợp lệ |
| Nested class đọc private field/method của outer | Biên dịch và chạy hợp lệ |
| Hai nested class ngang hàng đọc private của nhau | Biên dịch và chạy hợp lệ |
| Private constructor giữa nested classes | Chỉ truy cập trong source-level scope hợp lệ |
| `Class.getNestHost` | Các members chỉ đúng host |
| `Class.isNestmateOf` | Nestmates trả true; top-level khác trả false |
| `Class.getNestMembers` | Chứa host và members mong đợi, không dựa thứ tự |
| Local/anonymous class | Truy cập field và nest host đúng khi biên dịch target 11 |
| Bytecode `--release 11` | `NestMembers` trên host và `NestHost` trên member |
| Bytecode `--release 8` để so sánh | Thấy bridge accessor khi compiler cần, không nhầm là code nguồn |
| Reflection same nest | Đọc private field hợp lệ khi caller cùng nest |
| Reflection outside nest | Không tự đọc được private nếu không có quyền |
| Mixed/stale class file | Build pipeline phát hiện, clean build giải quyết |
| Class loader/agent/shading | Không làm mất hoặc làm sai nest attributes |
| Java 11 compatibility | Toolchain target 11, chương trình chạy trên JDK hợp lệ |

Kiểm thử không nhất thiết phải dùng một JDK 8 runtime. Dùng JDK được bảo trì để **phân tích class files target 8**; mục tiêu là xác nhận sự khác biệt do JEP 181, không vận hành runtime lỗi thời.

## 17. Bài tập thực hành

### Bài 1 — Phân tích quyền truy cập

Chạy `NestmateAccessDemo.java`. Với mỗi dòng output, chỉ rõ **caller**, **class khai báo private member** và **nest host**. Giải thích vì sao `Reader` đọc được `Writer.writerSecret` dù không phải subclass.

### Bài 2 — So sánh static nested và inner class

Thay `private final class Inner` bằng một static nested class. Quan sát code đọc `value` của outer không còn dùng được nếu thiếu reference tới outer instance. Sửa constructor của nested class để nhận `NestmateAccessDemo owner`. Đây là bài về **outer instance**, không phải bài thay đổi nest permissions.

### Bài 3 — Private constructor

Thêm một `private static class Token` (được khai báo là một nested member) với constructor `private` và một nested factory class ngang hàng tạo `new Token(...)`. Kiểm tra compiler chấp nhận. Sau đó thử tạo Token từ một top-level class không có quyền; giải thích compile error.

### Bài 4 — Inspect Java 8 và Java 11 bytecode

Chạy các lệnh của phần 6 và trả lời:
1. Tại sao output của cả hai binary đều là `83`?
2. Target Java 8 có thể xuất hiện `access$...` nào?
3. `NestMembers` và `NestHost` xuất hiện trong file nào khi target 11?
4. Vì sao `--release 11` không thể chạy trên JVM 8?

### Bài 5 — Kiểm tra danh sách nest

Không tin rằng phần tử thứ 2 của `getNestMembers()` là `Reader`. Viết test dùng `Arrays.asList(...)` hoặc `Set.of(...)` so sánh membership theo `Class<?>`. Vì sao cách này bền vững hơn khi đổi JDK/compiler?

### Bài 6 — Local và anonymous

Chạy `LocalNestDemo.java`. Thêm một local class khác có thể đọc field `secret`. Kiểm tra `getNestHost()` và `isNestmateOf(...)`. Không dựa vào số thứ tự `$1`/`$2` của file name.

### Bài 7 — Reflection và module

Chạy `ReflectionNestDemo.java`. Vì sao `Field.get` thành công trong host, nhưng thất bại khi được gọi trong `Outsider`? Mô tả điều kiện để deep reflection vượt module boundaries hợp lệ khi framework có lý do chính đáng, và vì sao điều đó là **vấn đề khác** với nest access.

### Bài 8 — Debug lỗi sau nâng cấp

Một artifact đã có `Outer.class` target Java 8 nhưng `Outer$Inner.class` target Java 11. Runtime báo lỗi private access. Hãy đề xuất thứ tự kiểm tra:
- Version class files, `javap -v`;
- Metadata `NestHost`/`NestMembers`;
- Build cache/JAR packaging/shading;
- Class loader và runtime;
- Clean rebuild và chạy test.

Không sửa bằng cách mở mọi private member thành public.

### Checklist hoàn thành

- [ ] Biết nest-based access là **JEP 181 của Java 11**, chủ yếu thay đổi ở JVM/class file.
- [ ] Biết các lớp lồng truy cập private trong source **đã hợp lệ trước Java 11**.
- [ ] Phân biệt nest host, nest member, nestmates.
- [ ] Biết `NestMembers` trên host, `NestHost` trên member và quy tắc xác nhận quan hệ.
- [ ] Không nhầm cùng package/file/module với cùng nest.
- [ ] Dùng `getNestHost`, `getNestMembers`, `isNestmateOf` đúng từ Java 11.
- [ ] Chạy được bốn ví dụ: nest access, bytecode probe, local/anonymous và reflection.
- [ ] Phân biệt synthetic accessor target 8 và direct private access target 11.
- [ ] Hiểu điều kiện runtime package/class loader và nguy cơ mix class files.
- [ ] Không dùng reflection/`--add-opens` như giải pháp tùy tiện để vượt `private`.
- [ ] Giữ target/ứng dụng trên JDK được hỗ trợ, không phụ thuộc runtime legacy.

## 18. Tài liệu tham khảo chính thức và vẫn còn áp dụng

1. [OpenJDK — JEP 181: Nest-Based Access Control](https://openjdk.org/jeps/181) — mục tiêu, motivat​ion và thiết kế nest-based access.
2. [Java SE 11 — java.lang.Class](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html) — `getNestHost()`, `getNestMembers()`, `isNestmateOf(...)` (cùng xuất hiện từ Java 11).
3. [Java SE 11 — JVMS `4.7.28 NestHost](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28) — cấu trúc `NestHost` attribute.
4. [Java SE 11 — JVMS `4.7.29 NestMembers](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29) — cấu trúc `NestMembers` attribute.
5. [Java SE 11 — JVMS `5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4) — kiểm tra quyền truy cập private khi có nestmates.
6. [Java SE 11 — JLS `6.6 Access Control](https://docs.oracle.com/javase/specs/jls/se11/html/jls-6.html#jls-6.6) — quy tắc truy cập ở Java source.
7. [Java SE 11 — java.lang.invoke.MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — access modes và method-handle lookup.
8. [Oracle JDK 11 Release Notes — JEP 181](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html) — xác nhận thay đổi bytecode/JVM không thay ngữ nghĩa Java language.
9. [Oracle JDK 15 Release Notes — Nestmate validation changes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html) — bối cảnh hành vi khi nest metadata hỏng thay đổi theo các JDK.
10. [Java SE 25 — java.lang.Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html) — các reflection APIs về nest tiếp tục tồn tại trên JDK LTS hiện đại.

**Kết luận:** từ Java 11, JVM nhận biết **các lớp/interface cùng nest** và có thể kiểm tra quyền truy cập `private` trực tiếp, không cần compiler-generated synthetic bridge methods chỉ để mô phỏng điều vốn đã hợp lệ trong source Java. Muốn phân tích đúng, hãy kiểm tra **nest host/member** qua `Class` và `javap`, phân biệt nó với package/loader/module access, và giữ class files của cả nhóm lồng **được biên dịch/đóng gói nhất quán**.