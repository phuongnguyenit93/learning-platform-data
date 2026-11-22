# 2.3 Tên nhị phân, tên chuẩn và descriptor: chọn đúng dạng tên cho từng API

Trong Java, cùng một kiểu có thể mang nhiều **biểu diễn tên** tùy lớp ngôn ngữ, Reflection, class loader hay định dạng bytecode. Với `java.util.Map.Entry`, tên chuẩn là `java.util.Map.Entry`, tên nhị phân là `java.util.Map$Entry`, còn descriptor JVM là `Ljava/util/Map$Entry;`. Truyền đúng kiểu dữ liệu nhưng sai **dạng tên** có thể gây `ClassNotFoundException`, descriptor không hợp lệ hoặc lỗi khi nối kết động.

**Sau bài này, bạn có thể:** phân biệt canonical name, binary name, internal name và JVM descriptor; chọn đúng đầu vào cho `Class.forName`, `ClassLoader`, `ClassDesc`, `MethodType` và công cụ đọc bytecode; xử lý đúng lớp lồng nhau, mảng, kiểu nguyên thủy, lớp local/anonymous và generic.

## 1. Bốn dạng biểu diễn cần tách biệt

| Dạng | Dùng ở đâu | Ví dụ cho `java.util.Map.Entry` |
| --- | --- | --- |
| Tên chuẩn (*canonical name*) | Cách gọi kiểu có tên chuẩn trong ngôn ngữ Java; hiển thị, tài liệu | `java.util.Map.Entry` |
| Tên nhị phân (*binary name*) | Định danh lớp/interface đã biên dịch; nạp lớp bằng tên | `java.util.Map$Entry` |
| Tên nội bộ JVM (*internal name*) | Biểu diễn tên lớp trong nhiều cấu trúc class file | `java/util/Map$Entry` |
| Descriptor kiểu tham chiếu (*field/type descriptor*) | Trường, tham số, giá trị trả về, mô tả kiểu theo JVM | `Ljava/util/Map$Entry;` |

**Quy tắc ghi nhớ:** dấu chấm `.` ngăn package ở binary name; dấu `$` phân tách tên lớp thành viên (*member class/interface*) với lớp bao; dấu gạch chéo `/` ngăn package ở internal name; descriptor tham chiếu thêm `L` ở đầu và `;` ở cuối. Các phép biến đổi bằng chuỗi chỉ an toàn khi đã biết chính xác tên gốc và cấu trúc kiểu.

### 1.1. Canonical name

`Class.getCanonicalName()` trả về tên chuẩn khi kiểu có tên chuẩn, hoặc `null` nếu không có. Với một lớp thành viên, tên chuẩn dùng dấu chấm:

- `String.class.getCanonicalName()` → `java.lang.String`.
- `java.util.Map.Entry.class.getCanonicalName()` → `java.util.Map.Entry`.
- `String[][].class.getCanonicalName()` → `java.lang.String[][]`.
- Lớp local khai báo trong phương thức và lớp anonymous **không có canonical name**; kết quả là `null`.

Tên chuẩn thường hợp để trình bày trong tài liệu, log dành cho con người hoặc mã nguồn, nhưng **không được mặc định là chuỗi mà class loader chấp nhận**. Ngay cả tên chuẩn trông giống tên đầy đủ của một lớp, thành viên lồng nhau vẫn có binary name khác.

### 1.2. Binary name

Theo quy tắc đặt tên nhị phân của Java, lớp top-level thường có dạng `package.ClassName`; lớp thành viên có dạng `package.Outer$Inner`. Java cho phép `$` trong định danh, vì vậy **không thể cứ thấy `$` là suy ra chắc chắn ranh giới lớp lồng nhau**.

Với lớp hoặc interface thông thường (không phải mảng và không phải *hidden class*), `Class.getName()` trả về binary name. `Class.forName("java.util.Map$Entry")` và `ClassLoader.loadClass("java.util.Map$Entry")` dùng dạng tên này. Ngược lại, `Class.forName("java.util.Map.Entry")` sẽ tìm một binary name khác và thường ném `ClassNotFoundException`.

**Lưu ý:** tên nhị phân do trình biên dịch tạo cho lớp local/anonymous có thể chứa `$` và số thứ tự; đừng hard-code cấu trúc/tên sinh ra đó như một hợp đồng ổn định.

### 1.3. Internal name

Trong các vị trí phù hợp của class file, binary name được mã hóa sang internal form bằng cách thay **dấu chấm phân cách package** thành `/`, giữ nguyên `$` nằm trong tên thành viên. Ví dụ: `java/lang/String`, `java/util/Map$Entry`.

Internal name chưa phải descriptor của một kiểu tham chiếu: `java/lang/String` thiếu `L...;`. Các API hay công cụ thao tác class file có thể yêu cầu internal name, trong khi `Class.forName` không dùng dạng có `/`. Với mảng, nhiều vị trí trong class file sử dụng **array descriptor** (ví dụ `[Ljava/lang/String;`), vì vậy đừng cố tạo “internal name của mảng” bằng một phép thay thế dấu chấm chung.

### 1.4. JVM descriptor

Descriptor là cú pháp có cấu trúc mô tả **kiểu** hoặc **chữ ký kiểu của phương thức**. Nó phục vụ class file, JVM linkage, `MethodType` và các API constant description. Nó không phải tên lớp để đưa thẳng vào `Class.forName`.

Một descriptor kiểu tham chiếu là `L` + internal name + `;`: `Ljava/lang/String;`. Mảng đặt một dấu `[` cho mỗi chiều: `[I` là `int[]`; `[[Ljava/lang/String;` là `String[][]`. Descriptor phương thức có dạng `(tham_số_1tham_số_2...)kiểu_trả_về`: `(Ljava/lang/String;I)V` là phương thức nhận (`String`, `int`) và trả về `void`.

## 2. So sánh trên những kiểu dễ nhầm

| Kiểu Java | Canonical name | `Class.getName()` | JVM type descriptor |
| --- | --- | --- | --- |
| `java.lang.String` | `java.lang.String` | `java.lang.String` | `Ljava/lang/String;` |
| `java.util.Map.Entry` | `java.util.Map.Entry` | `java.util.Map$Entry` | `Ljava/util/Map$Entry;` |
| `int` | `int` | `int` | `I` |
| `int[]` | `int[]` | `[I` | `[I` |
| `String[]` | `java.lang.String[]` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `String[][]` | `java.lang.String[][]` | `[[Ljava.lang.String;` | `[[Ljava/lang/String;` |
| `Map.Entry[]` | `java.util.Map.Entry[]` | `[Ljava.util.Map$Entry;` | `[Ljava/util/Map$Entry;` |

Ở bảng trên, `Class.getName()` của **mảng tham chiếu** trông giống descriptor, nhưng **phần tên thành phần vẫn có dấu chấm package** (`[Ljava.lang.String;`). Descriptor JVM thật dùng `/` (`[Ljava/lang/String;`). Khác biệt nhỏ này rất quan trọng khi làm việc với `Class.forName` và `ClassDesc.ofDescriptor`.

### 2.1. Bảng mã kiểu nguyên thủy

| Ký tự descriptor | Kiểu | Ký tự descriptor | Kiểu |
| --- | --- | --- | --- |
| `B` | `byte` | `C` | `char` |
| `D` | `double` | `F` | `float` |
| `I` | `int` | `J` | `long` |
| `S` | `short` | `Z` | `boolean` |

`V` biểu thị `void` **ở vị trí kiểu trả về của phương thức**; không dùng `V` làm descriptor của một trường hay tham số. API `void.class.descriptorString()` vẫn trả về `"V"` để mô tả kiểu `void`.

### 2.2. Descriptor phương thức: đọc từ trái sang phải

| Khai báo Java (minh họa) | JVM method descriptor | Ý nghĩa |
| --- | --- | --- |
| `void log()` | `()V` | Không tham số, không có giá trị trả về |
| `int twice(int n)` | `(I)I` | Một `int` vào, một `int` ra |
| `String label(String key, int count)` | `(Ljava/lang/String;I)Ljava/lang/String;` | `String` rồi `int`, trả về `String` |
| `void accept(String[] values)` | `([Ljava/lang/String;)V` | Một tham số `String[]`, trả về `void` |

**Không có dấu phẩy hoặc dấu cách** giữa các tham số trong descriptor. Dấu ngoặc `()` chỉ danh sách tham số; phần sau `)` là kiểu trả về. Tên phương thức (ví dụ `label`) và modifier như `static` không nằm trong bản thân method descriptor. Không đưa tên biến, generic argument hoặc `throws` vào descriptor.

## 3. API nào nhận dạng nào?

| Tình huống / API | Giá trị đúng và lý do |
| --- | --- |
| Viết tên kiểu trong mã nguồn | `java.util.Map.Entry`, `String[]`; cú pháp kiểu ở mức ngôn ngữ |
| Hiển thị tên có thể đọc | `clazz.getCanonicalName()` (kiểm tra `null`), hoặc `clazz.getTypeName()` nếu muốn tên thân thiện cho mảng |
| Lấy tên để nạp lớp thường | `clazz.getName()` khi `clazz` là lớp/interface thông thường; `Class.forName("java.util.Map$Entry")` |
| Nạp lớp bằng `ClassLoader` | `loader.loadClass("java.util.Map$Entry")`, dùng binary name của lớp/interface; không truyền descriptor |
| Nạp **lớp mảng** qua `Class.forName` | `Class.forName("[Ljava.lang.String;")` hoặc `Class.forName("[I")`; dạng tên mảng mà `Class.getName()` trả về |
| Lấy descriptor kiểu từ `Class<?>` | `clazz.descriptorString()`; ví dụ `String[].class.descriptorString()` → `[Ljava/lang/String;` |
| Làm việc với `java.lang.constant.ClassDesc` | `ClassDesc.of("java.util.Map$Entry")` với binary name; `ClassDesc.ofDescriptor("Ljava/util/Map$Entry;")` với descriptor |
| Tạo descriptor phương thức | `MethodType.methodType(void.class, String.class, int.class).toMethodDescriptorString()` → `(Ljava/lang/String;I)V` |
| Phân tích descriptor phương thức | `MethodType.fromMethodDescriptorString("(Ljava/lang/String;I)V", loader)` → `MethodType` |
| Tìm phương thức qua Reflection | `clazz.getDeclaredMethod("name", String.class, int.class)`: tên phương thức + các `Class<?>` tham số, **không** phải một descriptor chuỗi |
| Tra `MethodHandle` với `Lookup.findVirtual` | Cần receiver `Class<?>`, tên phương thức và `MethodType`, không tự ghép binary name thành descriptor |
| Đọc bytecode bằng `javap -s` | Công cụ in JVM descriptor của trường/phương thức |
| Đọc resource bằng `ClassLoader.getResource` | Đường dẫn tài nguyên như `demo/Message.class` (không có dấu `L...;`); đây là *resource path*, không phải tên kiểu |

Đừng suy ra từ tên method có chữ “name” rằng nó luôn cần canonical name. Hãy xem hợp đồng tham số: **binary name**, **descriptor**, **internal name**, **Class object**, **MethodType** hay **resource path** là các đối tượng khác nhau.

## 4. Ví dụ Java 17+ chạy được

Tạo đúng một tệp `NameFormsDemo.java` với nội dung sau:

```java
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodType;
import java.util.Map;

public class NameFormsDemo {
    public static void main(String[] args) throws Exception {
        Class<?> nested = Map.Entry.class;
        System.out.println("canonical = " + nested.getCanonicalName());
        System.out.println("binary    = " + nested.getName());
        System.out.println("descriptor= " + nested.descriptorString());
        System.out.println("array name= " + String[].class.getName());
        System.out.println("array desc= " + String[].class.descriptorString());
        System.out.println("array canonical = " + String[].class.getCanonicalName());
        System.out.println("int array name= " + int[].class.getName());
        System.out.println("loaded    = " + Class.forName("java.util.Map$Entry").getSimpleName());

        MethodType mt = MethodType.methodType(void.class, String.class, int.class);
        System.out.println("method    = " + mt.toMethodDescriptorString());
        System.out.println("parsed    = " + MethodType.fromMethodDescriptorString(
                "(Ljava/lang/String;I)V", NameFormsDemo.class.getClassLoader()));
        System.out.println("classDesc = "
                + ClassDesc.ofDescriptor("Ljava/util/Map$Entry;").descriptorString());

        class Local {}
        Runnable anonymous = new Runnable() { public void run() {} };
        System.out.println("local canonical = " + Local.class.getCanonicalName());
        System.out.println("anonymous canonical = "
                + anonymous.getClass().getCanonicalName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (ví dụ Java 17 hoặc Java 21):

```bash
javac --release 17 NameFormsDemo.java
java NameFormsDemo
```

`stdout` chính xác:

```text
canonical = java.util.Map.Entry
binary    = java.util.Map$Entry
descriptor= Ljava/util/Map$Entry;
array name= [Ljava.lang.String;
array desc= [Ljava/lang/String;
array canonical = java.lang.String[]
int array name= [I
loaded    = Entry
method    = (Ljava/lang/String;I)V
parsed    = (String,int)void
classDesc = Ljava/util/Map$Entry;
local canonical = null
anonymous canonical = null
```

Giải thích: `getCanonicalName()` và `getName()` cho ra hai cách gọi khác nhau của `Map.Entry`; `descriptorString()` tạo mã JVM có `L...;`. Mảng dùng encoding bắt đầu bằng `[`; `Class.forName` nạp thành công lớp thành viên bằng **binary name**. `MethodType` tạo/đọc method descriptor mà không tự ghép chuỗi. Hai kiểu local/anonymous là ví dụ trực tiếp cho trường hợp **không có canonical name**.

Dùng thêm `javap` trên lớp vừa biên dịch:

```bash
javap -s -p NameFormsDemo
```

Trong kết quả, phương thức `main(String[])` có descriptor `([Ljava/lang/String;)V`; `([Ljava/lang/String;)V` gồm một tham số mảng `String[]` và trả về `void`. `javap -s` là cách đối chiếu descriptor do trình biên dịch ghi vào class file.

## 5. Chuyển đổi và xử lý mảng đúng cách

Khi đã có đối tượng `Class<?>`, hãy **hỏi API theo mục tiêu** thay vì tự nối/ký tự hóa tên:

```java
Class<?> type = java.util.Map.Entry[].class;

String canonical = type.getCanonicalName();  // java.util.Map.Entry[]
String runtimeName = type.getName();          // [Ljava.util.Map$Entry;
String descriptor = type.descriptorString();  // [Ljava/util/Map$Entry;
```

Đây là **đoạn minh họa** (không phải chương trình độc lập). Lớp mảng không nạp bằng `Class.forName("java.util.Map.Entry[]")` hoặc `Class.forName("[Ljava/util/Map$Entry;")`. Khi cần nạp qua `Class.forName`, hãy dùng đúng **tên lớp mảng ở dạng `Class.getName()`**, ví dụ `Class.forName("[Ljava.util.Map$Entry;")`. Khi cần descriptor JVM, dùng `[Ljava/util/Map$Entry;`.

Với nguyên thủy, `Class.forName("int")` không phải cách tìm `int.class`; dùng trực tiếp `int.class` hoặc ánh xạ rõ ràng đến `int.class`. `Class.forName("[I")` có thể lấy lớp mảng `int[]`, vì tên lớp mảng tuân theo quy tắc khác với tên primitive đơn lẻ.

**Không viết bộ chuyển đổi tổng quát** kiểu `canonical.replace('.', '$')` hoặc `binary.replace('.', '/')` rồi mặc định đúng. Có thể có nhiều dấu chấm package và lớp thành viên, tên lớp chứa `$` hợp lệ, cùng các trường hợp local, anonymous và hidden class. Nếu đầu vào duy nhất là chuỗi nguồn `a.b.Outer.Inner`, cần biết ranh giới package/lớp thực tế trước khi xây binary name. Tốt nhất giữ `Class<?>`, `ClassDesc` hoặc `MethodType` càng lâu càng tốt.

## 6. Những trường hợp đặc biệt trong dynamic runtime

### 6.1. Local, anonymous và hidden class

- Lớp local/anonymous trả về `null` từ `getCanonicalName()` nhưng vẫn có `Class<?>`; tên do compiler tạo ra không phù hợp để cấu hình cố định hoặc tự suy đoán.
- Với *hidden class* (ví dụ tạo qua `MethodHandles.Lookup.defineHiddenClass`), `Class.getName()` **không phải binary name thông thường**; tên có phần hậu tố nội bộ. `descriptorString()` của hidden class cũng không phải nominal descriptor có thể đưa tùy ý vào `ClassDesc.ofDescriptor`. Hãy thao tác bằng `Class<?>` và lookup hợp lệ thay vì cố nạp hidden class bằng một tên chuỗi.
- `getSimpleName()` chỉ lấy tên ngắn, ví dụ `Entry`; nó không có package và không bảo đảm định danh duy nhất. `getTypeName()` hữu ích cho hiển thị (đặc biệt là mảng), không phải hợp đồng chung cho `Class.forName`.

### 6.2. Tên đúng chưa đủ xác định một lớp lúc chạy

Trong hệ thống plugin/hot reload/multiple class loaders, hai lớp có thể có **cùng binary name và cùng descriptor** nhưng do hai class loader khác nhau định nghĩa. Chúng vẫn là hai kiểu runtime khác nhau. Vì vậy khi xử lý `ClassNotFoundException`, `ClassCastException` hoặc `LinkageError`, kiểm tra **class loader, module và visibility** cùng với dạng tên; đừng kết luận mọi lỗi đến từ việc thay `.` bằng `$`.

`Class.forName(name)` có thể kích hoạt khởi tạo lớp; khi cần tránh khởi tạo trong lúc tra cứu, dùng overload `Class.forName(name, false, loader)` với loader phù hợp. `Class.forName` không tự biến chuỗi canonical của lớp member thành binary name.

### 6.3. Generic signature khác JVM descriptor

Giả sử một field Java khai báo `List<String> names;`. Vì *type erasure*, **field descriptor** là `Ljava/util/List;`, không chứa `String`. Thông tin tham số kiểu nếu được lưu có thể nằm trong thuộc tính `Signature`, ví dụ `Ljava/util/List<Ljava/lang/String;>;` — đây là **generic signature**, không phải field descriptor hợp lệ.

Tương tự, `String`, `String[]` và `List<String>` là các biểu diễn khác nhau: descriptor chỉ ghi loại runtime đã bị xóa kiểu nếu có generic. Để đọc kiểu generic, dùng API như `Field.getGenericType()` hoặc `Method.getGenericReturnType()` và kiểm tra `Type` / `ParameterizedType`; không trông đợi `Class.descriptorString()` giữ `<String>`.

## 7. Quy trình chọn dạng tên khi tích hợp API

1. **Xác định đích nhận.** API yêu cầu `Class<?>`, binary name, JVM descriptor, internal name hay đường dẫn tài nguyên? Đọc chữ ký và Javadoc của đúng API.
2. **Nếu có `Class<?>`**, ưu tiên `getName()` cho lớp thường / tên mảng dùng với `Class.forName`, `getCanonicalName()` cho hiển thị có kiểm tra `null`, `descriptorString()` cho cú pháp JVM.
3. **Nếu có phương thức**, ưu tiên `MethodType` để tạo/đọc method descriptor. Khi chọn overload Reflection, dùng `Class<?>[]` tham số đúng thứ tự và đúng kiểu (primitive `int` khác boxed `Integer`).
4. **Nếu phải nhận chuỗi từ cấu hình**, nêu rõ định dạng kỳ vọng và kiểm tra ở biên: ví dụ “binary name: `java.util.Map$Entry`”, hoặc “JVM descriptor: `Ljava/util/Map$Entry;`”. Đừng nhận một trường “className” mơ hồ mà đoán cách chuyển.
5. **Khi lỗi phát sinh**, log giá trị đầu vào và API được gọi, class loader liên quan, rồi so lại dạng tên. Với binary name, có thể thử `Class.forName(name, false, loader)` trong ngữ cảnh loader phù hợp; với descriptor, thử các API parser như `MethodType.fromMethodDescriptorString` hoặc `ClassDesc.ofDescriptor` và xử lý lỗi định dạng.

### Những lỗi thường gặp

| Sai hoặc dễ nhầm | Đúng theo ngữ cảnh |
| --- | --- |
| `Class.forName("java.util.Map.Entry")` | `Class.forName("java.util.Map$Entry")` |
| `Class.forName("java.lang.String[]")` | `Class.forName("[Ljava.lang.String;")` hoặc `String[].class` |
| `Class.forName("Ljava/lang/String;")` | `Class.forName("java.lang.String")` nếu muốn nạp lớp; dùng descriptor với `ClassDesc.ofDescriptor` |
| `ClassDesc.ofDescriptor("Ljava.lang.String;")` | `ClassDesc.ofDescriptor("Ljava/lang/String;")` |
| `MethodType.fromMethodDescriptorString("(String,int)void", loader)` | `MethodType.fromMethodDescriptorString("(Ljava/lang/String;I)V", loader)` |
| Xem `Ljava/util/List<Ljava/lang/String;>;` như field descriptor | Hiểu đó là generic signature; descriptor bị xóa kiểu là `Ljava/util/List;` |
| Coi `getCanonicalName()` luôn trả chuỗi | Kiểm tra `null` đối với local/anonymous và các kiểu không có canonical name |

## 8. Tự kiểm tra nhanh

**Tình huống A:** plugin nhận chuỗi tên lớp thành viên `com.acme.Outer.Inner` nhưng gọi `Class.forName` không tìm thấy. Hãy xác minh khai báo và package, dùng binary name `com.acme.Outer$Inner` nếu đó thực sự là member class. Đồng thời kiểm tra loader của plugin.

**Tình huống B:** bytecode cần mô tả phương thức `boolean check(String[] names, long timeout)`. Descriptor đúng là `([Ljava/lang/String;J)Z`: `[Ljava/lang/String;` cho `String[]`, `J` cho `long`, `Z` cho `boolean`.

**Tình huống C:** log in ra `[Ljava.lang.String;`, còn thư viện bytecode yêu cầu descriptor. Không đưa nguyên log đó vào thư viện; lấy `String[].class.descriptorString()` để được `[Ljava/lang/String;`.

**Tình huống D:** `getCanonicalName()` trả `null`. Đây có thể là kiểu không có tên chuẩn, chẳng hạn local/anonymous; không suy luận lớp “chưa nạp” từ kết quả này.

## Tài liệu chuẩn để đối chiếu

- *Java Language Specification, Java SE 17*, mục 6.7 (*Fully Qualified Names and Canonical Names*) và 13.1 (*The Form of a Binary*): https://docs.oracle.com/javase/specs/jls/se17/html/
- *Java Virtual Machine Specification, Java SE 17*, mục 4.2.1 (*Binary Class and Interface Names*) và 4.3.2–4.3.3 (*Field/Method Descriptors*): https://docs.oracle.com/javase/specs/jvms/se17/html/
- JDK 17 `java.lang.Class`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JDK 17 `java.lang.invoke.MethodType`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html

**Điểm mấu chốt khi tích hợp dynamic runtime:** *canonical name* giúp con người đọc; *binary name* định danh lớp/interface khi nạp theo tên; *internal name* thuộc lớp cấu trúc JVM; *descriptor* mô tả kiểu và chữ ký phương thức. Chọn theo hợp đồng của API và ưu tiên các đối tượng kiểu chuẩn thay vì tự ghép chuỗi.
