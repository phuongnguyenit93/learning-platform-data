# Phân biệt String Pool với Constant Pool của class file trong Java

**String Pool** và **constant pool trong file `.class`** đều chứa từ “pool”, nhưng phục vụ **hai nhiệm vụ hoàn toàn khác nhau**:

- **Constant pool của class file** là một **bảng cấu trúc dữ liệu nằm trong bytecode `.class`**, mô tả các hằng số và liên kết ký hiệu mà mã Java đã biên dịch sử dụng. Trong đó có thể có mô tả của một chuỗi literal, tên lớp, tên phương thức, kiểu dữ liệu, hằng số số học và nhiều thành phần khác. Đây không phải kho tập hợp các đối tượng `java.lang.String` đang chạy.
- **String Pool** là cơ chế **dùng chung đối tượng `String` theo nội dung trong lúc chương trình chạy** (*string interning*). Khi hai tham chiếu cùng trỏ tới một `String` đã được intern, chúng có cùng identity. Pool này liên quan tới Java runtime và `String.intern()`, không phải cấu trúc bảng `constant_pool` ghi trên đĩa.

Một literal như `"java"` có thể được **mô tả** bởi mục `CONSTANT_String_info` trong class file; khi JVM sử dụng literal đó, JVM thu được **tham chiếu đến một `String` được intern**. Đây là mối liên hệ giữa hai khái niệm, chứ không phải bằng chứng rằng chúng là cùng một vùng nhớ hoặc cùng một bảng.

## 1. So sánh hai khái niệm

| Tiêu chí | Constant pool của class file | String Pool (intern pool) |
|---|---|---|
| **Mục đích** | Biểu diễn hằng và các tham chiếu ký hiệu trong định dạng `.class` | Dùng chung `String` có nội dung bằng nhau |
| **Giai đoạn chính** | Sinh ra khi biên dịch/biến đổi bytecode; đọc khi JVM nạp và liên kết lớp | Được sử dụng trong quá trình thực thi |
| **Chứa gì** | Các entry có kiểu/tag như `CONSTANT_Utf8`, `CONSTANT_String`, `CONSTANT_Class`, `CONSTANT_Methodref`, `CONSTANT_Integer`, `CONSTANT_InvokeDynamic`… | Các đối tượng `String` được intern (và cơ chế ánh xạ để tìm chúng) |
| **Phạm vi mô tả** | **Mỗi class file** có bảng riêng | Cơ chế interning bảo đảm các literal/các chuỗi interned có nội dung tương đương dùng tham chiếu canonical theo hợp đồng của Java |
| **Tra cứu/quan sát** | `javap -v TenLop`; nhìn thấy các mục `#n = …` và lệnh bytecode tham chiếu chúng | Xem hành vi literal, `intern()` và toán tử `==`; `javap` không in ra toàn bộ runtime String Pool |
| **Quan hệ với object identity** | Entry trong `.class` **không tự nó là** đối tượng `String` | Hai tham chiếu đến cùng instance `String` thì `==` là `true` |
| **Có mọi đối tượng `String`?** | Không; chỉ có metadata/hằng của class file đó | Không; chuỗi mới tạo bằng `new String(...)` hoặc phép toán runtime không mặc nhiên được intern |
| **Có mọi loại hằng?** | Có nhiều loại thông tin, không chỉ chuỗi | Chỉ liên quan đến `String` được intern |

**Không nhầm:** Một số tài liệu còn nói tới **run-time constant pool** theo đặc tả JVM. Đây là biểu diễn **theo từng class/interface** được dẫn xuất từ `constant_pool` của `.class` khi lớp được JVM tạo, phục vụ liên kết và thực thi (`JVMS `2.5.5`). Nó cũng **không đồng nghĩa** với String Pool dùng để intern các đối tượng `String`.

## 2. Trong `.class`, một string literal được lưu thế nào?

Giả sử mã nguồn dùng:

```java
public class ClassPoolView {
    static final String MESSAGE = "Con" + "stant";

    public static String getMessage() {
        return "Constant";
    }
}
```

Java compiler có thể nhận ra `"Con" + "stant"` là **biểu thức hằng tại thời điểm biên dịch** (*compile-time constant expression*). Với `javac` thông thường, giá trị của `MESSAGE` là `"Constant"` và getter trả về literal có cùng nội dung.

Trong định dạng class file, những cấu trúc liên quan thường là:

```text
CONSTANT_String_info
    tag          = 8   (CONSTANT_String)
    string_index = n   (chỉ tới CONSTANT_Utf8_info)

CONSTANT_Utf8_info
    tag    = 1   (CONSTANT_Utf8)
    length = ...
    bytes  = ... (nội dung dùng modified UTF-8)
```

- `CONSTANT_String_info` là một **entry có chỉ số** trong bảng; nó trỏ đến entry `CONSTANT_Utf8_info` mô tả nội dung chuỗi. Nó **không chứa con trỏ tới một đối tượng Java `String` đã nằm sẵn trong class file**.
- `CONSTANT_Utf8_info` là dạng dữ liệu có độ dài và mảng byte trong định dạng `.class`. Nó chứa **modified UTF-8 (MUTF-8)**, khác UTF-8 chuẩn ở một số trường hợp (chẳng hạn NUL và ký tự ngoài BMP). Không đồng nhất “các byte UTF-8 trong `.class`” với “cách `String` được lưu trong heap”.
- `CONSTANT_Utf8_info` còn biểu diễn tên lớp, tên phương thức, descriptor và nhiều thông tin **không phải literal**. Thấy `Utf8 java` trong output của `javap` **không đủ** để kết luận một đối tượng `String` tên `"java"` đã được intern.
- `CONSTANT_String_info` chỉ là **mô tả một chuỗi có thể được tải bởi JVM**. Sau khi phân giải, JVM có thể sử dụng tham chiếu tới `String` thực tế theo quy tắc interning.
- Một class file có rất nhiều entry kiểu khác: mô tả lớp, trường, phương thức, kiểu hàm, số nguyên, số thực, v.v. Chúng không thuộc String Pool.

### Quan sát bằng `javap`

Biên dịch và xem bytecode:

```bash
javac -encoding UTF-8 ClassPoolView.java
javap -v -c ClassPoolView
```

Trong output sẽ có một mục **`Constant pool:`** chứa các entry có chỉ số `#n`. Một phần **minh họa cấu trúc** (chỉ số `#n` thay đổi theo compiler/JDK và chi tiết class, **không** phải output nguyên văn cố định):

```text
Constant pool:
   #a = String             #b             // Constant
   #b = Utf8               Constant
   ...
   #c = Utf8               MESSAGE
   ...
   #d = Utf8               ConstantValue
   ...

public static java.lang.String getMessage();
  Code:
     ...
     ldc      #a             // String Constant
     areturn
```

Ở đây, `ldc` nạp một giá trị tham chiếu tới `String` tương ứng với hằng literal sau khi JVM xử lý mục `CONSTANT_String`. Trình biên dịch cũng có thể đặt **`ConstantValue`** cho trường `static final String MESSAGE` vì đây là một constant variable. Chi tiết thứ tự entry và các mục bổ sung phụ thuộc bytecode được sinh ra.

Nhìn vào `javap -v` là cách tốt để kiểm tra **class file constant pool**. Tuy nhiên, output đó không thể tự cho biết toàn bộ các `String` nào đang được intern ở runtime, địa chỉ đối tượng, số lượng đối tượng trong pool, hay thuật toán lưu trữ của JVM.

## 3. Vì sao literal lại dùng chung một `String` khi chạy?

Java Language Specification yêu cầu các **string literal** và chuỗi là giá trị của **constant expression** được intern. Khi các literal có cùng nội dung được dùng, chúng tham chiếu tới **cùng một instance `String`**; quy tắc này có ý nghĩa kể cả khi literal ở các lớp khác nhau.

Ví dụ:

```java
String a = "java";
String b = "java";
System.out.println(a == b); // true
```

Hai literal có cùng nội dung được dùng chung tham chiếu. Dù mỗi class file có thể có một entry `CONSTANT_String` cho `"java"`, các entry đó vẫn **khác nhau về mặt metadata**; runtime đảm bảo chuỗi literal được intern tương ứng là một đối tượng canonical.

### Cầu nối từ `CONSTANT_String` đến `String`

Có thể hình dung luồng xử lý điển hình như sau:

```text
Mã nguồn Java: "java"
         |
         v
Biên dịch thành class file
         |
         v
constant_pool của class file
  CONSTANT_String -> CONSTANT_Utf8 ("java")
         |
         v
JVM nạp/liên kết và dùng hằng chuỗi
  (ví dụ khi thực thi lệnh ldc)
         |
         v
Phân giải/thu được tham chiếu String
theo quy tắc interning
         |
         v
Đối tượng java.lang.String canonical
         |
         v
Lệnh Java sử dụng tham chiếu đó
```

Đây là **mô hình khái niệm**, không phải lời khẳng định chính xác thời điểm JVM tạo đối tượng. JVM có thể tối ưu và phân giải hằng vào thời điểm được phép theo đặc tả; việc JVM phân giải sớm hoặc muộn không làm thay đổi quy tắc observable của literal và `intern()`.

Tương tự, **run-time constant pool** có thể giữ giá trị/tham chiếu đã phân giải cho class đang chạy; điều đó không biến toàn bộ run-time constant pool thành String Pool.

## 4. Ba khái niệm hay bị gọi cùng là “constant pool”

| Tên chính xác | Khi nào tồn tại/được dùng | Cách hiểu |
|---|---|---|
| **Class-file constant pool** (`constant_pool`) | Cấu trúc trong định dạng `.class` | Các entry ký hiệu và hằng số do compiler hoặc trình xử lý bytecode ghi ra |
| **Run-time constant pool** | Theo từng class/interface do JVM tạo khi nạp class; dùng trong liên kết/thực thi | Biểu diễn runtime được dẫn xuất từ class-file constant pool, có thể bao gồm các giá trị/đích đã phân giải |
| **String Pool / intern pool** | Khi ứng dụng chạy và có literal/`intern()` | Cơ chế dùng chung instance `java.lang.String` theo nội dung |

**Câu hỏi “String Pool nằm ở đâu?”** có thể được trả lời ở hai mức:

- **Theo hợp đồng Java:** các chuỗi interned cung cấp tham chiếu canonical. JLS không yêu cầu người lập trình suy luận một địa chỉ nhớ vật lý cụ thể từ từ “pool”.
- **Theo triển khai:** JVM như HotSpot quản lý dữ liệu intern với cấu trúc runtime riêng; cách tổ chức, kích thước và chính sách quản lý là chủ đề JVM/GC, có thể thay đổi theo phiên bản. Không nên ghi nhớ quy tắc kiểu “String Pool chắc chắn ở PermGen” cho Java hiện đại, vì PermGen đã bị loại bỏ khỏi HotSpot từ Java 8.

Quan trọng hơn vị trí vật lý là **nguyên tắc nào làm hai tham chiếu cùng một đối tượng**: literal và constant expression được intern; `intern()` cho phép nhận tham chiếu canonical; string tạo từ runtime không mặc nhiên được intern.

## 5. Sai lầm thường gặp và cách kiểm tra

| Nhận định | Vấn đề | Cách kiểm tra/hiểu đúng |
|---|---|---|
| “String Pool chính là bảng `Constant pool:` trong `javap`.” | `javap` đọc metadata `.class`, không liệt kê heap object canonical | Phân biệt file format với hành vi identity của `String` runtime |
| “`CONSTANT_Utf8_info` là một đối tượng `String`.” | Entry này là dữ liệu bytes trong class file | Phân biệt mô tả dạng binary với Java object |
| “Có `String` trong class-file constant pool thì nó chắc chắn đã được khởi tạo lúc compile.” | Compiler không tạo object Java runtime cho file `.class` | Đối tượng `String` tương ứng được JVM thu được khi runtime dùng hằng |
| “Hai class có `CONSTANT_String` riêng nên literal cùng nội dung là hai objects.” | Metadata riêng không đồng nghĩa instance riêng | Literal được intern theo nội dung |
| “`new String("x")` lấy đúng đối tượng interned vì literal `"x"` được intern.” | `new` tạo đối tượng riêng | Dùng `==` để quan sát identity, `equals` để so nội dung |
| “`static final` luôn có một entry hằng compile-time.” | Phải xem initializer có là constant expression không | So sánh `static final String A="x"` với `static final String B=new String("x")` |
| “Hai chuỗi `equals` nhau thì `==` cũng phải đúng.” | Nội dung và object identity là hai phép so sánh khác nhau | Dùng `equals` cho logic nghiệp vụ |
| “`intern()` luôn là cách tối ưu hiệu năng.” | Việc intern cũng có chi phí tra cứu và quản lý pool; hiệu quả phụ thuộc tập dữ liệu | Chỉ dùng khi đã xác định lợi ích và kiểm chứng bằng đo đạc |

## 6. Tài liệu đặc tả để đối chiếu

- [Java Language Specification, 3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): quy tắc string literal và interning.
- [Java Language Specification, 15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): biểu thức hằng tại compile-time.
- [Java Virtual Machine Specification, 4.4 — The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4): cấu trúc `CONSTANT_String_info` và `CONSTANT_Utf8_info`.
- [Java Virtual Machine Specification, 2.5.5 — Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.5): khái niệm run-time constant pool.

**Ghi nhớ:** `constant_pool` trong `.class` là **bảng mô tả hằng và ký hiệu**; String Pool là **cơ chế dùng chung đối tượng `String` lúc chạy**. Entry `CONSTANT_String_info` có thể là đầu mối để JVM thu được tham chiếu `String` interned, nhưng entry của class file và đối tượng được intern là **hai thứ khác nhau**. Khi cần kiểm tra, dùng `javap -v` cho cấu trúc `.class`, và dùng `==`/`equals`/`intern()` trong chương trình để phân biệt identity với nội dung.