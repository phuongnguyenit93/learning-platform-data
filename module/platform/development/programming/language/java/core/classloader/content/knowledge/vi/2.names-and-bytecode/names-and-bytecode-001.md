# Tên nhị phân, tên chuẩn và tên nội bộ của lớp trong Java

> **Phạm vi:** Java Core → ClassLoader → Tên và bytecode. Bài này giải thích ba cách biểu diễn tên của lớp/interface trong mã nguồn, Java Reflection và định dạng `.class`, cùng cách dùng đúng chúng khi nạp lớp hoặc đọc bytecode. Các ví dụ chạy với Java 17+.

## 1. Vì sao cùng một lớp có nhiều tên?

Xét một lớp thành viên nằm trong `package demo`:

```java
package demo;

public class Outer {
    public static class Inner {}
}
```

Cùng một kiểu `Inner` có thể được nhắc đến bằng nhiều cách, tùy ngữ cảnh:

| Ngữ cảnh | Chuỗi | Ý nghĩa |
| --- | --- | --- |
| Mã nguồn Java / tên chuẩn (canonical) | `demo.Outer.Inner` | Cách viết tên kiểu bằng dấu chấm, phù hợp cách tham chiếu trong Java source. |
| Tên nhị phân (binary) | `demo.Outer$Inner` | Tên định danh lớp sau biên dịch; `$` nối lớp bao và lớp thành viên. |
| Tên nội bộ JVM (internal) | `demo/Outer$Inner` | Dạng tên lớp dùng trong cấu trúc class file và nhiều phần của bytecode. |
| Field descriptor (kiểu tham chiếu) | `Ldemo/Outer$Inner;` | Mô tả **kiểu** đối tượng trong descriptor; thêm `L` và `;` bao quanh internal name. |
| Tên tài nguyên class file | `demo/Outer$Inner.class` | Đường dẫn tài nguyên tương ứng, thường tìm qua classpath/module. |

**Không có một phép thay thế ký tự dùng được cho mọi trường hợp.** Cụ thể, dấu `.` giữa `Outer` và `Inner` trong tên chuẩn chuyển thành `$` ở tên nhị phân, còn dấu `.` ngăn *package* chuyển thành `/` trong tên nội bộ. ClassLoader nhận tên nhị phân; bộ phân tích bytecode thường cần tên nội bộ hoặc descriptor.

## 2. Tên chuẩn (canonical name)

Tên chuẩn là tên của kiểu theo quy tắc đặt tên trong ngôn ngữ Java (JLS §6.7):

- Lớp/interface cấp cao nhất: `java.util.Map`, `demo.Outer`.
- Lớp/interface thành viên: `java.util.Map.Entry`, `demo.Outer.Inner`.
- Kiểu mảng có phần tử có tên chuẩn: `java.lang.String[]`, `demo.Outer.Inner[][]`.
- Kiểu nguyên thủy: `int`, `boolean`; `void` cũng có cách hiển thị riêng qua đối tượng `Class`.

Trong Reflection, `Class.getCanonicalName()` trả về tên chuẩn **hoặc `null`** nếu kiểu không có tên chuẩn. Lớp local (khai báo trong phương thức/khối lệnh) và lớp anonymous thông thường **không có tên chuẩn**; vì vậy không được mặc định kết quả luôn là chuỗi.

Tên chuẩn hữu ích để giải thích cho người đọc hoặc tạo code Java. Nó không phải tham số chung cho `Class.forName`: với lớp thành viên, chuỗi `demo.Outer.Inner` là tên chuẩn, không phải tên nhị phân mà API này cần.

## 3. Tên nhị phân (binary name)

Theo JLS §13.1, tên nhị phân của các loại lớp/interface thông thường có quy tắc:

| Loại khai báo | Ví dụ tên nhị phân | Điểm cần nhớ |
| --- | --- | --- |
| Top-level | `demo.Outer` | Trùng tên chuẩn. |
| Member class/interface | `demo.Outer$Inner` | Ghép tên nhị phân lớp bao, `$`, tên đơn của member. |
| Local class | Dạng `demo.Outer$1Local` | Có phần chữ số do trình biên dịch tạo; **không dựa vào số cụ thể**. |
| Anonymous class | Dạng `demo.Outer$1` | Không có tên đơn/canonical; thứ tự đánh số không phải giao kèo ổn định để code phụ thuộc. |

`Class.getName()` trả về tên nhị phân cho lớp/interface thông thường không phải array và không phải hidden class. `Class.forName("demo.Outer$Inner")` hay `ClassLoader.loadClass("demo.Outer$Inner")` sử dụng tên nhị phân để tìm lớp đó (các overload khác nhau có cơ chế khởi tạo/loader khác nhau).

Lưu ý thêm:

- **Static nested class và non-static inner class** đều dùng `$` trong tên nhị phân; chữ `static` không thay đổi dạng tên.
- Ký tự `$` có thể nằm trong identifier Java hợp lệ. Do đó **không thể xác định chắc quan hệ lồng nhau chỉ bằng cách cắt chuỗi tại `$`**. Khi cần biết cấu trúc khai báo, dùng metadata/Reflection như `getDeclaringClass()`, `getEnclosingClass()`, `isMemberClass()`, `isLocalClass()` và `isAnonymousClass()`.
- Tên nhị phân của local/anonymous class là chi tiết trình biên dịch; sửa mã nguồn có thể đổi các file `$1`, `$2`. Tránh lưu cứng chúng làm API hay định danh bền vững.
- Một lớp còn có **định danh khi chạy** gắn với class loader đã định nghĩa nó: hai loader khác nhau có thể định nghĩa hai lớp khác nhau cùng tên nhị phân. Tên không tự bảo đảm hai `Class<?>` là cùng kiểu.

## 4. Tên nội bộ (internal name) trong JVM

JVMS §4.2.1 quy định *internal form* của tên nhị phân lớp/interface: thay dấu chấm **phân tách các thành phần package** bằng dấu gạch chéo `/`. Phần `$Inner` của tên member được giữ nguyên:

```text
Tên nhị phân:  java.util.Map$Entry
Tên nội bộ:   java/util/Map$Entry
```

Trong tệp `.class`, mục `CONSTANT_Class_info` của constant pool tham chiếu chuỗi tên nội bộ, chẳng hạn `demo/Outer$Inner`. Lệnh thao tác kiểu như `new`, `checkcast` hay `instanceof` cũng tham chiếu biểu diễn kiểu thông qua constant pool. Khi nhìn `javap -v` hoặc dùng thư viện thao tác bytecode, dấu `/` là chuyện bình thường.

**Không lẫn internal name với descriptor:**

- Internal name của lớp: `java/lang/String`.
- Field descriptor của tham chiếu đến lớp đó: `Ljava/lang/String;`.
- Descriptor của kiểu `int`: `I` (không có internal name của một *class* nguyên thủy).
- Descriptor của `String[]`: `[Ljava/lang/String;`.
- Method descriptor của phương thức nhận `String` và `int`, trả về `void`: `(Ljava/lang/String;I)V`.

Trong descriptor: `B` byte, `C` char, `D` double, `F` float, `I` int, `J` long, `S` short, `Z` boolean, `V` void (chỉ hợp lệ ở vị trí kiểu trả về của method descriptor), `L<internal-name>;` là reference, còn mỗi dấu `[` tăng một chiều mảng. Java generic bị xóa kiểu ở descriptor thông thường: `List<String>` có field descriptor `Ljava/util/List;`; nếu còn thông tin generic, đó là metadata `Signature` riêng.

Có thể hình dung đường đi của một lớp member như sau:

```text
Mã Java:             demo.Outer.Inner
                           |
                           | javac
                           v
Binary name:         demo.Outer$Inner
                           |
                           | JVM class-file encoding
                           v
Internal name:       demo/Outer$Inner
                           |
                           | field/method descriptor
                           v
Reference descriptor: Ldemo/Outer$Inner;
```

Đây là **các cách biểu diễn trong từng ngữ cảnh**, không phải các loại lớp khác nhau.

## 5. Quan sát bằng chương trình Java 17+

Tạo file `demo/NamesDemo.java`:

```java
package demo;

public class NamesDemo {
    static class Member {}

    public static void main(String[] args) throws Exception {
        show("top", NamesDemo.class);
        show("member", Member.class);
        show("String[]", String[].class);
        show("int[][]", int[][].class);
        show("primitive", int.class);

        class Local {}
        Object anonymous = new Object() {};
        System.out.println("local canonical null: "
                + (Local.class.getCanonicalName() == null));
        System.out.println("anonymous simple empty: "
                + anonymous.getClass().getSimpleName().isEmpty());
        System.out.println("loaded member: "
                + Class.forName("demo.NamesDemo$Member").getName());
    }

    static void show(String label, Class<?> type) {
        System.out.println(label + ": name=" + type.getName()
                + ", canonical=" + type.getCanonicalName()
                + ", simple=" + type.getSimpleName()
                + ", type=" + type.getTypeName());
    }
}
```

Biên dịch/chạy từ thư mục chứa `demo/`:

```bash
javac -d out demo/NamesDemo.java
java -cp out demo.NamesDemo
```

Đầu ra xác định trên Java 17+:

```text
top: name=demo.NamesDemo, canonical=demo.NamesDemo, simple=NamesDemo, type=demo.NamesDemo
member: name=demo.NamesDemo$Member, canonical=demo.NamesDemo.Member, simple=Member, type=demo.NamesDemo$Member
String[]: name=[Ljava.lang.String;, canonical=java.lang.String[], simple=String[], type=java.lang.String[]
int[][]: name=[[I, canonical=int[][], simple=int[][], type=int[][]
primitive: name=int, canonical=int, simple=int, type=int
local canonical null: true
anonymous simple empty: true
loaded member: demo.NamesDemo$Member
```

Diễn giải các method `Class`:

| Method | Công dụng | Lưu ý |
| --- | --- | --- |
| `getName()` | Binary name cho lớp/interface thường; mã dạng dấu `[` cho array; tên keyword cho primitive/void | **Không** luôn là tên nhị phân của lớp thường. |
| `getCanonicalName()` | Tên chuẩn để biểu diễn kiểu trong source | Có thể là `null` cho local, anonymous hoặc loại không có canonical name. |
| `getSimpleName()` | Tên ngắn; với anonymous class là chuỗi rỗng | Với array, thêm `[]` vào tên đơn của phần tử. |
| `getTypeName()` | Cách hiển thị tên kiểu dễ đọc hơn với array | Cho `String[]` là `java.lang.String[]`, không phải `[Ljava.lang.String;`. |
| `getPackageName()` | Tên package của kiểu | Không được dùng để suy diễn quan hệ member/local bằng cách cắt chuỗi. |

Ví dụ in `getName()` của local/anonymous class không được đưa vào đầu ra cố định vì phần số là chi tiết do compiler sinh; chương trình chỉ kiểm tra đặc tính được quy định.

## 6. Trường hợp mảng, primitive và hidden class

Với **mảng**, `Class.getName()` dùng một dạng gần với descriptor nhưng **tên lớp thành phần có dấu chấm**:

| Kiểu Java | `Class.getName()` | JVM field descriptor |
| --- | --- | --- |
| `int` | `int` | `I` |
| `int[]` | `[I` | `[I` |
| `int[][]` | `[[I` | `[[I` |
| `java.lang.String` | `java.lang.String` | `Ljava/lang/String;` |
| `java.lang.String[]` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `demo.Outer.Inner[][]` | `[[Ldemo.Outer$Inner;` | `[[Ldemo/Outer$Inner;` |

Bởi vậy, công thức `name.replace('.', '/')` chỉ giúp đổi tên **lớp/interface bình thường** từ dạng binary sang internal; với array, bạn đang làm việc với một biểu diễn kiểu khác. Khi triển khai framework hay bytecode tooling, hãy sử dụng bộ phân tích descriptor phù hợp thay vì ghép hoặc cắt chuỗi tùy tiện.

Với **primitive/void**, `int.class.getName()` trả `"int"` và `void.class.getName()` trả `"void"`; không thể nạp chúng bằng `Class.forName("int")` hay `Class.forName("void")`. Chúng không có file `int.class` hoặc `void.class` thông thường để ClassLoader tìm.

Từ các phiên bản Java hiện đại còn có **hidden class** (chẳng hạn được tạo qua `MethodHandles.Lookup.defineHiddenClass`). Theo API `Class.getName()` Java 17, tên hidden class có dạng `N/suffix`; tên này không phải binary name thông thường dùng để `Class.forName` tìm lại. Không suy ra mọi tên được in bởi `getName()` đều có thể nạp bằng tên đó.

## 7. ClassLoader và đường dẫn tài nguyên: chọn đúng tên

Ba thao tác phổ biến sử dụng ba hình thức khác nhau:

```java
// Binary name, với $ cho lớp thành viên:
Class<?> type = Class.forName("demo.NamesDemo$Member");

// ClassLoader nhận tên nhị phân của lớp thường:
Class<?> same = NamesDemo.class.getClassLoader()
        .loadClass("demo.NamesDemo$Member");

// Tên tài nguyên .class dùng dấu /, không dùng tên canonical:
var url = NamesDemo.class.getClassLoader()
        .getResource("demo/NamesDemo$Member.class");
```

Đoạn trên **minh họa cách gọi khi lớp `NamesDemo` có trên classpath**, không phải chương trình độc lập. `type == same` là `true` nếu cả hai lời gọi trả về cùng lớp do cùng defining loader; nếu lựa chọn loader khác đi thì không thể suy luận như vậy chỉ từ tên. `getResource` có thể trả `null` nếu tài nguyên không được tìm thấy hoặc không thể truy cập trong cấu hình/module cụ thể.

Một vài quy tắc cần phân biệt:

1. `Class.forName(String)` dùng tên nhị phân cho lớp thường; tên canonical của member như `"demo.NamesDemo.Member"` không nạp được lớp `Member` ở ví dụ. Với array, API còn chấp nhận dạng array name do `Class.getName()` trả về, ví dụ `"[I"`, `"[Ljava.lang.String;"`; nó không nhận cú pháp Java `"java.lang.String[]"`.
2. `ClassLoader.loadClass(String)` nhận tên nhị phân của lớp/interface để nạp, không phải đường dẫn `demo/NamesDemo$Member.class` hay internal name `demo/NamesDemo$Member`. Đừng giả định nó xử lý array descriptor như `Class.forName`.
3. `ClassLoader.getResource("demo/NamesDemo$Member.class")` dùng đường dẫn với `/`, **không có dấu `/` đầu tiên**; còn `NamesDemo.class.getResource("/demo/NamesDemo$Member.class")` cho đường dẫn tuyệt đối theo API `Class`.
4. Việc `loadClass` tìm được lớp nhưng `getResource` không trả file là điều có thể xảy ra ở loader tự định nghĩa, class được tạo động hoặc cấu hình module. Nạp lớp và tìm tài nguyên là hai tác vụ khác nhau.

## 8. Kiểm tra trực tiếp tên trong bytecode

Với file đã tạo ở mục 5, chạy:

```bash
javap -v -classpath out 'demo.NamesDemo$Member'
```

Lệnh trên dùng cách quote phù hợp với shell Unix để giữ ký tự `$` khỏi bị mở rộng. Trên Windows PowerShell, cũng có thể dùng dấu nháy đơn như vậy. Tìm các vị trí như:

```text
this_class: ... // demo/NamesDemo$Member
```

Dòng trên là **mẫu rút gọn minh họa**, vì số chỉ mục constant pool phụ thuộc nội dung bytecode và phiên bản compiler. Thử tiếp `javap -v -classpath out demo.NamesDemo` để quan sát `InnerClasses`, `EnclosingMethod` (nếu có) và các chuỗi descriptor trong constant pool. Dòng lệnh `javap` nhận tên lớp theo cú pháp của công cụ; phần annotation/comment trong output có thể hiển thị internal name.

Quan hệ giữa file name và class name cũng giúp debug:

- Source: `demo/NamesDemo.java`.
- Output top-level class: `out/demo/NamesDemo.class`.
- Output member: `out/demo/NamesDemo$Member.class`.
- Đường dẫn resource: `demo/NamesDemo$Member.class`.
- Chuỗi cần cho `Class.forName`: `demo.NamesDemo$Member`.

Đường dẫn vật lý hoặc nội dung JAR/module phụ thuộc cách build và class loader, nên không đồng nhất tên file với định danh kiểu lúc chạy.

## 9. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `ClassNotFoundException` khi dùng `"demo.Outer.Inner"` | Truyền canonical thay vì binary name của member | Dùng `"demo.Outer$Inner"`, xác minh có đúng class trên classpath/module path. |
| Không tìm được resource `demo.Outer$Inner.class` | Resource name phải dùng `/` | Dùng `demo/Outer$Inner.class` với `ClassLoader.getResource`. |
| Descriptor `Ljava/lang/String;` không được API loadClass chấp nhận | Descriptor khác binary name | Dùng `java.lang.String` với API load lớp thường. |
| `getCanonicalName()` gây `NullPointerException` khi thao tác chuỗi | Local/anonymous/hidden class có thể không có canonical name | Kiểm tra `null`, hoặc dùng API name phù hợp mục đích. |
| Thay `$` thành `.` rồi nạp lớp thất bại | Cắt chuỗi nhị phân theo cấu trúc source mà loader không hiểu | Giữ binary name cho nạp lớp, chỉ dùng canonical name để hiển thị. |
| Hai lớp in cùng `getName()` nhưng cast thất bại | Khác defining class loader | Kiểm tra `clazz.getClassLoader()` và định danh runtime của từng `Class<?>`. |
| `NoClassDefFoundError` trong quá trình liên kết/nạp | Có thể thiếu dependency transitively hoặc lỗi xác định/khởi tạo lớp; không đủ bằng chứng chỉ từ dấu `/` | Xem nguyên nhân gốc (`Caused by`), classpath/module, loader và tên được JVM báo. |

**Quy trình debug thực dụng:** xác định API đang cần *binary name*, *internal name*, *descriptor* hay *resource path* → xem `getName()`/`getCanonicalName()` và loader của lớp → dùng `javap -v` để xác nhận tên nội bộ/descriptor → mới kiểm tra classpath, module path, quyền truy cập và class loader.

## 10. Tự kiểm tra

1. Một member interface `com.acme.Api.Response` có binary name, internal name và descriptor là gì?  
   **Đáp án:** `com.acme.Api$Response`; `com/acme/Api$Response`; `Lcom/acme/Api$Response;`.
2. `String[][].class.getName()` và field descriptor của kiểu này khác nhau thế nào?  
   **Đáp án:** `[[Ljava.lang.String;` so với `[[Ljava/lang/String;`.
3. `Local.class.getCanonicalName()` phải trả tên gì khi `Local` là lớp khai báo trong phương thức?  
   **Đáp án:** `null`. `Local.class.getName()` vẫn có tên do compiler tạo nhưng không nên phụ thuộc số thứ tự.
4. Vì sao `Class.forName("java.util.Map.Entry")` không nạp member interface `Entry`?  
   **Đáp án:** Chuỗi đó là canonical name; API yêu cầu binary name `java.util.Map$Entry`.
5. Hai class loader nạp cùng binary name có bắt buộc tạo một lớp duy nhất không?  
   **Đáp án:** Không; định danh lớp lúc chạy còn phụ thuộc defining loader.

## 11. Nguồn chuẩn để tra cứu

- [JLS §6.7 — Fully Qualified Names and Canonical Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.7): các quy tắc tên chuẩn.
- [JLS §13.1 — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1): định nghĩa tên nhị phân và cấu trúc class file.
- [JVMS §4.2.1 — Binary Class and Interface Names](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.2.1): biểu diễn tên nội bộ.
- [JVMS §4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): descriptor của field/method.
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getCanonicalName`, `getSimpleName` và `getTypeName`.
