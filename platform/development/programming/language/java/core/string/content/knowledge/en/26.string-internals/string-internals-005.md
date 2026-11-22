# Constant pool và vai trò của `Constable`, `ConstantDesc` trong Java String

Khi đọc tài liệu về `String`, ta dễ gặp ba thuật ngữ rất giống nhau: **constant pool**, **String pool** và **constant descriptor**. Chúng liên hệ với nhau nhưng phục vụ những mục đích khác nhau:

- **Constant pool của class file**: bảng thông tin hằng và tham chiếu ký hiệu trong tệp `.class`, được JVM sử dụng khi nạp và chạy mã.
- **String pool / string interning**: cơ chế cho phép những chuỗi có cùng nội dung dùng chung một đối tượng `String` chuẩn hóa (*canonical*), ví dụ qua literal và `intern()`.
- **`Constable` và `ConstantDesc`**: API từ Java 12 để **mô tả một giá trị dưới dạng hằng có thể biểu diễn danh nghĩa (*nominally*)** và, khi cần, phân giải mô tả ấy trong một ngữ cảnh truy cập phù hợp.

Chúng **không phải ba tên gọi của cùng một vùng bộ nhớ**. Hiểu đúng sự khác biệt giúp tránh nhầm lẫn về việc literal được lưu ở đâu, vì sao `"abc" == "abc"` thường là `true` và tại sao `String` triển khai cả hai interface `Constable`, `ConstantDesc`.

## 1. Constant pool trong tệp `.class` là gì?

Một class file hợp lệ có cấu trúc bảng `constant_pool`. Đây là **bảng dữ liệu nhị phân**, chứa nhiều kiểu entry phục vụ bytecode và liên kết biểu tượng, chứ không phải một kho chỉ chứa chuỗi Java.

Một số entry điển hình:

| Loại entry trong class file | Vai trò |
| --- | --- |
| `CONSTANT_Utf8` | Lưu tên lớp, tên phương thức, descriptor, các chuỗi văn bản và dữ liệu ký hiệu khác theo dạng modified UTF-8 của JVM |
| `CONSTANT_String` | Biểu diễn một **hằng `String`**, tham chiếu đến một entry `CONSTANT_Utf8` chứa nội dung |
| `CONSTANT_Class` | Tham chiếu ký hiệu đến lớp hoặc interface |
| `CONSTANT_NameAndType` | Tên và descriptor của field hoặc method |
| `CONSTANT_Fieldref`, `CONSTANT_Methodref` | Tham chiếu ký hiệu đến field và method |
| `CONSTANT_Integer`, `CONSTANT_Long`, ... | Giá trị số được biểu diễn trực tiếp bằng các loại entry tương ứng |
| `CONSTANT_MethodHandle`, `CONSTANT_MethodType` | Thông tin method handle và method type |
| `CONSTANT_Dynamic`, `CONSTANT_InvokeDynamic` | Hỗ trợ hằng động và liên kết lời gọi động; **không phải cùng một loại entry** |

Khi viết:

```java
String text = "Java";
```

Trình biên dịch thường ghi một entry `CONSTANT_String` tham chiếu đến `CONSTANT_Utf8` chứa nội dung `Java`. Bytecode có thể dùng lệnh `ldc` để nạp tham chiếu tới đối tượng `String` tương ứng.

Điều này **không có nghĩa toàn bộ đối tượng `String`, gồm header và dữ liệu runtime, được nhét nguyên trong tệp `.class`**. Tệp `.class` chỉ chứa **biểu diễn nhị phân và ký hiệu** để JVM tạo/lấy đối tượng khi thực thi.

Một sơ đồ đơn giản:

```text
Java source:       String s = "Java";
                           |
                           v
Class file:       CONSTANT_String --> CONSTANT_Utf8("Java")
                           |
                      bytecode ldc
                           |
                           v
JVM runtime:      tham chiếu tới String canonical "Java"
```

Trong JVM còn có **run-time constant pool** gắn với mỗi class/interface được nạp: nó được dẫn xuất từ cấu trúc `constant_pool` trong class file và chứa dữ liệu/tham chiếu đã hoặc sẽ được JVM phân giải. Khái niệm run-time constant pool này cũng **khác với cơ chế intern chuỗi**.

## 2. String pool là gì? Vì sao literal thường dùng chung đối tượng?

Java quy định rằng các **string literal có cùng nội dung** biểu diễn cùng một đối tượng `String`. Chuỗi tạo bằng cách ghép **các biểu thức hằng ở thời điểm biên dịch** cũng có thể trở thành cùng literal đã được intern.

```java
String a = "Java";
String b = "Ja" + "va"; // biểu thức hằng, được gộp lúc biên dịch

System.out.println(a == b);       // true
System.out.println(a.equals(b));  // true
```

`==` so sánh **cùng tham chiếu** (cùng đối tượng); `equals` so sánh **nội dung chuỗi**. Nhờ cơ chế interning dành cho literal và biểu thức hằng, `a == b` là `true` trong ví dụ này.

Nhưng một chuỗi được tạo mới không mặc nhiên trỏ đến cùng đối tượng:

```java
String a = "Java";
String c = new String("Java");

System.out.println(a == c);          // false
System.out.println(a.equals(c));     // true
System.out.println(a == c.intern());  // true
```

- `new String("Java")` tạo một đối tượng `String` mới riêng biệt (dù cùng nội dung).
- `intern()` trả về tham chiếu đến đại diện canonical tương ứng với nội dung ấy.
- `equals` mới là lựa chọn thông thường để so sánh **giá trị văn bản**.

Tại đây, **String pool** là ý tưởng/cơ chế quản lý các tham chiếu `String` canonical trong JVM, chứ không phải một bảng entry `CONSTANT_String` độc lập ở file `.class`. Không nên suy ra địa chỉ vật lý chính xác của chuỗi hoặc cơ chế quản lý bộ nhớ chỉ từ từ “pool”. Vị trí lưu trữ và tối ưu hóa nội bộ có thể thay đổi theo phiên bản và triển khai JVM.

### Ghép chuỗi ở runtime có giống hằng lúc biên dịch không?

`"Ja" + "va"` được tính như biểu thức hằng. Ngược lại:

```java
String left = "Ja";
String runtime = left + "va";
```

`runtime` là kết quả **ghép ở runtime** vì `left` là biến cục bộ thông thường, không phải biến hằng. Không nên dựa vào `runtime == "Java"` để kiểm tra nội dung. Trình biên dịch/JVM có thể tối ưu hóa ghép chuỗi, nhưng **tính đúng đắn của chương trình phải dựa trên `equals`**. Có thể gọi `runtime.intern()` nếu thực sự cần tham chiếu canonical và hiểu chi phí của việc đó.

## 3. `Constable` — giá trị có thể tự mô tả như một hằng

Từ Java 12, package `java.lang.constant` cung cấp interface:

```java
public interface Constable {
    Optional<? extends ConstantDesc> describeConstable();
}
```

Một kiểu `Constable` có những giá trị **có thể mô tả dưới dạng một hằng có thể biểu diễn trong mô hình constant pool của class file**. `describeConstable()` tạo mô tả danh nghĩa khi khả thi.

Điều cần nhớ:

- `Constable` thể hiện **khả năng mô tả**, không có nghĩa đối tượng đang nằm trong String pool.
- Phương thức trả về `Optional` vì **không phải mọi instance của mọi kiểu `Constable` đều mô tả được**. Khi không thể tạo mô tả, nó có thể trả về `Optional.empty()`.
- Kết quả là một `ConstantDesc`, biểu diễn giá trị bằng API mô tả hằng, chứ không bắt buộc là đối tượng runtime ban đầu.

Ví dụ, một số kiểu có biểu diễn hằng quen thuộc như `String`, `Integer`, `Long`, `Float` và `Double` có thể tự đóng vai trò là descriptor; `Class` dùng `ClassDesc` làm mô tả danh nghĩa tương ứng. Các kiểu khác có thể cần descriptor phức tạp hơn.

**Không nhầm `Constable` với `final` hay `static final`**. `final` nói về khả năng gán lại biến/field; một object có thể triển khai `Constable` dù được tạo mới ở runtime và không nằm trong một field `final` nào.

## 4. `ConstantDesc` — mô tả danh nghĩa và phân giải hằng

Interface `ConstantDesc` thuộc cùng package và cung cấp phương thức chính:

```java
Object resolveConstantDesc(MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

Đây là chữ ký khái quát của interface; các kiểu triển khai có thể trả về kiểu cụ thể hơn.

Phương thức `resolveConstantDesc(lookup)` yêu cầu hệ thống **phân giải một mô tả** thành một giá trị runtime trong ngữ cảnh tra cứu/truy cập được chỉ định. Đối với descriptor biểu diễn lớp, phương thức hoặc hằng động, bước phân giải có thể cần truy cập metadata, class loader, bootstrap hoặc gặp lỗi truy cập.

Phân biệt vai trò:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| `Constable.describeConstable()` | “Giá trị này có thể cung cấp một mô tả hằng danh nghĩa không?” |
| `ConstantDesc` | “Mô tả hằng được biểu diễn bằng API như thế nào?” |
| `ConstantDesc.resolveConstantDesc(lookup)` | “Từ mô tả này, có thể phân giải được giá trị runtime nào trong ngữ cảnh `lookup`?” |

**Không phải mọi `ConstantDesc` đều là entry đang tồn tại sẵn trong constant pool của một class file cụ thể.** API giúp mô tả các hằng tải được (*loadable constants*) và hỗ trợ các công cụ dựng bytecode, mô tả bootstrap, phân giải biểu tượng. Nó không xác nhận rằng JVM đã lưu một bản sao của mọi descriptor vào class file hay intern mọi giá trị được phân giải.

### Ví dụ `ClassDesc`

`ClassDesc` là một dạng `ConstantDesc` mô tả lớp bằng descriptor JVM:

```java
ClassDesc desc = ClassDesc.of("java.lang.String");

System.out.println(desc.descriptorString());
// Ljava/lang/String;

System.out.println(
        desc.resolveConstantDesc(MethodHandles.lookup()) == String.class);
// true
```

Hai dòng trên là **đoạn mã minh họa đặt trong phương thức** có khai báo hoặc xử lý `ReflectiveOperationException` và đã import `java.lang.constant.ClassDesc`, `java.lang.invoke.MethodHandles`.

`"Ljava/lang/String;"` là **mô tả tên kiểu** (JVM field descriptor), không phải đối tượng `Class<?>`. Việc phân giải `ClassDesc` mới có thể trả về đối tượng `Class` tương ứng. Với tên lớp không hợp lệ hoặc lớp không truy cập được trong ngữ cảnh phù hợp, việc phân giải có thể thất bại.

## 5. Tại sao `String` triển khai **cả hai interface**?

Từ Java 12, `String` triển khai cả `Constable` và `ConstantDesc`. Với chính `String`, mô tả danh nghĩa của một giá trị có thể chính là **giá trị chuỗi đó**.

Nói cách khác:

1. `String.describeConstable()` trả về `Optional` có chứa **chính chuỗi hiện tại**.
2. Vì `String` cũng là một `ConstantDesc`, giá trị chuỗi ấy được dùng làm descriptor.
3. `String.resolveConstantDesc(lookup)` đơn giản trả về **chính đối tượng chuỗi**; nó không cần tra cứu class như `ClassDesc`.

Thử với một chuỗi được tạo mới:

```java
String fresh = new String("Java");

ConstantDesc desc = fresh.describeConstable().orElseThrow();
Object resolved = desc.resolveConstantDesc(MethodHandles.lookup());

System.out.println(desc == fresh);     // true
System.out.println(resolved == fresh); // true
System.out.println(resolved == "Java"); // false
```

Đoạn này cần import `java.lang.constant.ConstantDesc`, `java.lang.invoke.MethodHandles` và được đặt trong phương thức khai báo/giải quyết `ReflectiveOperationException`.

Phép so sánh cuối là điểm then chốt: **một `String` là `Constable`/`ConstantDesc` không có nghĩa nó đã được intern**. `resolveConstantDesc` của `String` trả về chính instance mà ta đang cầm, kể cả nó được tạo bởi `new String(...)`. Để lấy chuỗi canonical, phải dùng `intern()` riêng khi phù hợp.

Đừng nhầm “có thể mô tả thành hằng” với “chương trình hiện tại đã lưu một bản của chuỗi này trong class file”.

## 6. Ví dụ Java 17+ chạy độc lập

Tạo file `StringConstantDemo.java` với nội dung:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.Constable;
import java.lang.constant.ConstantDesc;
import java.lang.invoke.MethodHandles;
import java.util.Optional;

public class StringConstantDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        String literal = "Java";
        String folded = "Ja" + "va";
        String fresh = new String("Java");

        System.out.println("literal == folded   : " + (literal == folded));
        System.out.println("literal == fresh    : " + (literal == fresh));
        System.out.println("literal.equals(fresh): "
                + literal.equals(fresh));
        System.out.println("literal == interned : "
                + (literal == fresh.intern()));

        Constable constable = fresh;
        Optional<? extends ConstantDesc> nominal =
                constable.describeConstable();

        System.out.println("descriptor present  : "
                + nominal.isPresent());

        ConstantDesc descriptor = nominal.orElseThrow();
        System.out.println("descriptor == fresh : "
                + (descriptor == fresh));

        Object resolved = descriptor.resolveConstantDesc(
                MethodHandles.lookup());

        System.out.println("resolved == fresh   : "
                + (resolved == fresh));
        System.out.println("resolved == literal : "
                + (resolved == literal));

        ClassDesc classDesc = ClassDesc.of("java.lang.String");
        System.out.println("class descriptor    : "
                + classDesc.descriptorString());
        System.out.println("resolved String.class: "
                + (classDesc.resolveConstantDesc(MethodHandles.lookup())
                        == String.class));
    }
}
```

Biên dịch và chạy:

```bash
javac StringConstantDemo.java
java StringConstantDemo
```

Stdout:

```text
literal == folded   : true
literal == fresh    : false
literal.equals(fresh): true
literal == interned : true
descriptor present  : true
descriptor == fresh : true
resolved == fresh   : true
resolved == literal : false
class descriptor    : Ljava/lang/String;
resolved String.class: true
```

Giải thích từng phần:

- `literal` và `folded` là cùng chuỗi interned vì `"Ja" + "va"` là biểu thức hằng ở thời điểm biên dịch.
- `fresh` do `new String("Java")` tạo ra nên khác tham chiếu với literal, dù `equals` trả `true`.
- `fresh.intern()` trả về tham chiếu canonical và bằng `literal`.
- `describeConstable()` của `String` trả về mô tả hiện diện; mô tả ấy chính là `fresh`.
- `resolveConstantDesc(...)` trên một `String` descriptor cũng trả về `fresh`, **không tự động intern**.
- `ClassDesc` mô tả tên lớp; sau khi phân giải, nó tương ứng với đối tượng `String.class`.

`main` khai báo `throws ReflectiveOperationException` vì các lệnh phân giải descriptor được phép ném checked exception theo API. Với code ứng dụng cần xử lý thất bại phân giải, hãy dùng `try/catch` hay khai báo ngoại lệ ở tầng phù hợp.

## 7. Tự quan sát constant pool bằng `javap`

Sau khi biên dịch file ở mục 6, dùng:

```bash
javap -v StringConstantDemo
```

Đây là công cụ JDK để xem metadata và bytecode của `.class`. Trong kết quả thường có phần:

```text
Constant pool:
  ...
  ... = String             #...            // Java
  ... = Utf8                               Java
  ...
```

Đoạn trên là **sơ đồ rút gọn của định dạng đầu ra**, không phải transcript có số index cố định. Số thứ tự entry, vị trí và cách tối ưu có thể khác theo trình biên dịch và phiên bản JDK. Để nhìn thấy lệnh bytecode, có thể dùng:

```bash
javap -c StringConstantDemo
```

Một lệnh `ldc` dùng entry tương ứng để nạp hằng chuỗi từ constant pool. **Đừng tìm đối tượng `fresh` ở dưới dạng một entry `String` mới chỉ vì nó xuất hiện qua `new String("Java")`**: đối tượng mới được tạo ở runtime, dù literal `Java` có mặt trong class file.

Ngoài chuỗi, class file còn có các entry mô tả tên lớp, method, field và các biểu thức hằng khác. Constant pool **phục vụ liên kết và thực thi bytecode**, chứ không cung cấp API để ứng dụng Java duyệt tất cả đối tượng `String` đang được intern.

### Mối quan hệ với `CONSTANT_Dynamic`

Từ Java 11, JVM có entry `CONSTANT_Dynamic` để hỗ trợ hằng được phân giải động thông qua bootstrap method. Trong API `java.lang.constant`, `DynamicConstantDesc` là một dạng descriptor để mô tả loại hằng động đó theo hướng danh nghĩa.

Không cần dùng `DynamicConstantDesc` chỉ để thao tác chuỗi thường ngày, và **`CONSTANT_Dynamic` không đồng nghĩa với “mọi chuỗi được tạo lúc runtime”**. Chuỗi nối hay `new String(...)` thông thường không tự trở thành một constant dynamic.

## 8. Sơ đồ phân biệt ba tầng

```text
        Java source
  String s = "Java";
            |
            v
  [1] Class-file constant_pool
      CONSTANT_String --> CONSTANT_Utf8("Java")
            |
            | class loading / execution / ldc
            v
  [2] JVM String interning
      canonical String object: "Java"
            |
            | String API (có thể gọi trên cả String không intern)
            v
  [3] Constable / ConstantDesc
      string.describeConstable() -> Optional chứa string
      descriptor.resolveConstantDesc(lookup) -> chính string
```

Sơ đồ cho biết **mối liên hệ**, không khẳng định ba tầng dùng chung một vùng nhớ. Tầng 1 là cấu trúc thông tin hằng trong class file; tầng 2 là quy tắc canonical reference đối với literal và `intern`; tầng 3 là interface Java cho biểu diễn/phân giải hằng dưới dạng danh nghĩa.

Đối với `String`, một giá trị có thể được tạo mà **không xuất phát trực tiếp từ literal** nhưng vẫn là `Constable` và `ConstantDesc`, vì đây là tính chất của kiểu `String` chứ không phải nhãn chỉ dành cho những instance nằm trong pool.

## 9. Những lỗi phổ biến

1. **Đồng nhất constant pool với String pool.** Constant pool của `.class` chứa rất nhiều loại entry; String pool liên quan đến tham chiếu canonical của các đối tượng `String` runtime.
2. **Cho rằng mọi `String` đều được intern.** `new String(...)` tạo instance khác. `String` có tính bất biến không đồng nghĩa với tự động canonical hóa tất cả giá trị.
3. **Dùng `==` để kiểm tra nội dung hai chuỗi.** `==` chỉ so sánh tham chiếu; dùng `equals` hoặc `Objects.equals` khi có thể có `null`.
4. **Cho rằng `String implements Constable` nghĩa là `String` luôn là compile-time constant.** Sai: kiểu hỗ trợ API mô tả hằng, không cam kết cách biểu thức được tính hoặc nơi instance được lưu.
5. **Cho rằng `describeConstable()` bắt buộc luôn có giá trị với mọi loại `Constable`.** Kết quả là `Optional`; một số kiểu/instance không mô tả được và có thể trả rỗng. Riêng `String` trả descriptor của chính nó.
6. **Cho rằng `resolveConstantDesc` luôn tạo đối tượng mới.** Với `String`, nó trả lại chính đối tượng hiện có; với các kiểu descriptor khác, hành vi phân giải phụ thuộc ý nghĩa descriptor.
7. **Cho rằng `ClassDesc` là `Class<?>`.** `ClassDesc` mô tả kiểu bằng dạng danh nghĩa; `resolveConstantDesc` mới tạo/thu được `Class<?>` trong ngữ cảnh phù hợp.
8. **Cho rằng `CONSTANT_Utf8` luôn là một chuỗi literal Java.** Nó cũng lưu tên, descriptor và metadata ký hiệu; chỉ `CONSTANT_String` dùng nội dung liên quan để biểu diễn hằng `String`.
9. **Cố suy ra vị trí vật lý cụ thể của bộ nhớ từ từ “pool”.** Cấu trúc đặc tả và cách cài đặt JVM không phải một điều; hãy phân biệt bảo đảm ngôn ngữ với chi tiết của một JVM phiên bản cụ thể.
10. **Intern mọi chuỗi để tăng tốc một cách máy móc.** `intern()` có chi phí quản lý và tác động bộ nhớ; chỉ dùng khi có lý do đo đạc hoặc thiết kế rõ ràng.

## 10. Tự luyện tập

**Câu 1.** Với `String a = "x"; String b = "x";`, `a == b` là gì?

**Đáp án:** `true` vì hai literal có cùng nội dung dùng chung tham chiếu `String` canonical.

**Câu 2.** Với `String a = "x"; String b = new String("x");`, `a.equals(b)` và `a == b`?

**Đáp án:** `equals` là `true`, `==` là `false`. `b.intern() == a` là `true`.

**Câu 3.** `fresh.describeConstable()` có đồng nghĩa với `fresh.intern()` không?

**Đáp án:** Không. Với `String`, `describeConstable()` cung cấp descriptor là chính `fresh`; `intern()` tìm/trả về đối tượng chuỗi canonical theo nội dung.

**Câu 4.** `ClassDesc.of("java.lang.String")` có phải là `String.class` không?

**Đáp án:** Không. `ClassDesc` là một descriptor danh nghĩa. Khi phân giải thành công bằng `resolveConstantDesc(lookup)`, nó có thể trả về đối tượng `Class` tương ứng với `String.class`.

**Câu 5.** Có thể dùng `Constable` để kiểm tra một `String` được khai báo với `final` hay được đưa trực tiếp vào `.class` không?

**Đáp án:** Không. `Constable` mô tả khả năng của kiểu/giá trị trong API constant descriptor; nó không cung cấp nguồn gốc literal, thuộc tính `final` của biến hay nơi đối tượng đang nằm trong bộ nhớ.

**Câu 6.** Vì sao dùng `javap -v` và `==` trả lời hai câu hỏi khác nhau?

**Đáp án:** `javap -v` kiểm tra **entry và bytecode của class file**; `==` so sánh **tham chiếu object ở runtime**. Đây là hai tầng quan sát khác nhau.

## 11. Ghi nhớ và tài liệu chính thức

- **Class-file constant pool**: bảng hằng và tham chiếu ký hiệu phục vụ bytecode, gồm `CONSTANT_String` và nhiều loại entry khác.
- **String pool / `intern()`**: bảo đảm tham chiếu canonical cho cùng nội dung chuỗi theo hợp đồng của Java.
- **`Constable`**: một instance có thể cung cấp biểu diễn danh nghĩa bằng `describeConstable()`.
- **`ConstantDesc`**: mô tả giá trị hằng và hỗ trợ `resolveConstantDesc(lookup)`.
- **`String`**: vừa là `Constable` vừa là `ConstantDesc`, nhưng **không phải mọi instance `String` đều được intern**.

Tài liệu:
- [`String` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [`Constable` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/Constable.html)
- [`ConstantDesc` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ConstantDesc.html)
- [`ClassDesc` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ClassDesc.html)
- [JVM Specification `4.4 — The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4)
- [JVM Specification `5.1 — The Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.1)
