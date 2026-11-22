# Class.forName với tên nhị phân trong Java Reflection

## 1. Mục tiêu và ngữ cảnh

Trong Java Reflection, **`Class.forName(String name)`** tìm một lớp hoặc interface theo tên tại thời điểm chạy và trả về đối tượng `Class<?>` biểu diễn kiểu đó. Điểm quan trọng là chuỗi truyền vào phải theo **tên nhị phân (binary name)** của lớp/interface thông thường; tên bạn viết trong mã Java đôi khi khác tên này. Riêng mảng có cú pháp biểu diễn đặc biệt, còn primitive không tra cứu bằng `Class.forName("int")`.

Sau bài học, bạn có thể phân biệt tên đơn giản, canonical name và binary name; tra cứu chính xác top-level class, member class và array; giải thích quá trình nạp/khởi tạo; chọn overload/class loader phù hợp; và xử lý những lỗi tra cứu điển hình.

## 2. Binary name khác canonical name như thế nào?

**Binary name** là tên dùng để định danh lớp/interface trong biểu diễn nhị phân của Java, được quy định trong JLS §13.1. Với một lớp top-level, tên thường là tên package cộng tên lớp, ví dụ `java.lang.String`. Với một **lớp hoặc interface thành viên** nằm bên trong kiểu khác, binary name dùng dấu **`$`** giữa các cấp lớp, ví dụ `java.util.Map$Entry`, trong khi source Java viết `java.util.Map.Entry`.

| Kiểu | Tên trong Java source / canonical name | Tên phù hợp với `Class.forName` |
| --- | --- | --- |
| Top-level class | `java.lang.String` | `java.lang.String` |
| Top-level interface | `java.util.List` | `java.util.List` |
| Member interface | `java.util.Map.Entry` | `java.util.Map$Entry` |
| Nested member class | `com.example.Outer.Inner` | `com.example.Outer$Inner` |
| Lồng nhiều cấp | `com.example.Outer.Middle.Inner` | `com.example.Outer$Middle$Inner` |
| Mảng `String[]` | `java.lang.String[]` | `[Ljava.lang.String;` |
| Mảng `String[][]` | `java.lang.String[][]` | `[[Ljava.lang.String;` |
| Mảng `int[]` | `int[]` | `[I` |
| Primitive `int` | `int` | Dùng `int.class`, không dùng `Class.forName("int")` |

Ba API lấy tên từ đối tượng `Class`:

- `getSimpleName()`: tên ngắn, chẳng hạn `Inner`; không mang đủ thông tin package/outer class.
- `getCanonicalName()`: tên theo cú pháp source, chẳng hạn `com.example.Outer.Inner`. Local class và anonymous class thường không có canonical name, nên có thể trả về `null`.
- `getName()`: với class/interface thường trả về binary name, chẳng hạn `com.example.Outer$Inner`; với mảng trả về tên dạng đặc biệt như `[Ljava.lang.String;`; với primitive trả về `int`, `boolean`...

**Quy tắc thực hành:** Khi đã có `SomeType.class`, lấy `SomeType.class.getName()` để tạo chuỗi cho các kiểu class/interface và array, thay vì tự biến đổi dấu chấm thành `$`. Ngoại lệ là primitive hoặc `void`, vì chuỗi `getName()` của chúng không dùng để nạp lại qua `Class.forName`.

## 3. Cú pháp chính xác theo loại kiểu

### 3.1. Lớp/interface top-level

```java
Class<?> stringType = Class.forName("java.lang.String");
Class<?> listType = Class.forName("java.util.List");
```

Chuỗi là tên đầy đủ có package. Khác với compiler xử lý tên `String` trong mã nguồn, `Class.forName("String")` không tự thêm package `java.lang`. Nó thử tìm lớp đúng tên đã truyền.

### 3.2. Member class và member interface

```java
Class<?> entry = Class.forName("java.util.Map$Entry");
Class<?> nested = Class.forName("com.example.Outer$Inner");
```

Dòng thứ hai chỉ thành công khi class `com.example.Outer$Inner` thực sự tồn tại và thấy được bởi loader. Ví dụ này minh họa cú pháp, không giả định project có class đó. Trong `com.example.Outer$Inner`, dấu chấm phân cách package và kiểu top-level; dấu `$` phân cách outer/inner type. Không thay tất cả dấu chấm thành `$`.

Quy tắc đặt tên trên cũng áp dụng cho **non-static inner class**. Tuy vậy, tra cứu được `Class` không đồng nghĩa có thể tạo instance inner class bằng constructor không tham số: constructor của inner class thường cần tham chiếu ngầm đến đối tượng outer.

### 3.3. Kiểu mảng sử dụng tên dạng descriptor

Với mảng, chuỗi `Class.forName` chấp nhận gồm một ký tự `[` cho mỗi chiều và mã của kiểu thành phần:

- Với thành phần là class/interface: `L` + binary name + `;`, ví dụ `[Ljava.lang.String;`.
- Với primitive: dùng mã `Z` = boolean, `B` = byte, `C` = char, `D` = double, `F` = float, `I` = int, `J` = long, `S` = short.
- Với mảng hai chiều, thêm một dấu `[`: `[[I` cho `int[][]`, `[[Ljava.lang.String;` cho `String[][]`.

```java
Class<?> strings = Class.forName("[Ljava.lang.String;");
Class<?> ints = Class.forName("[I");
Class<?> matrix = Class.forName("[[I");
Class<?> entries = Class.forName("[Ljava.util.Map$Entry;");
```

Không dùng `"java.lang.String[]"` hoặc `"int[]"` với overload nhận tên. Đây là **dạng tên mảng**, không phải tên nhị phân của top-level class; cách lấy tên chắc chắn nhất là `String[].class.getName()` hay `int[].class.getName()`. Nạp lớp mảng không tự khởi tạo lớp thành phần của mảng.

### 3.4. Primitive, generic, local và anonymous class

`Class.forName("int")`, `Class.forName("void")` không phải cách lấy đối tượng `Class` của primitive/void; dùng `int.class`, `void.class`, `Integer.TYPE`. Cũng không truyền cú pháp generic `"java.util.List<java.lang.String>"`: tham số kiểu generic không nằm trong binary name của raw class `java.util.List`.

Tên local class hoặc anonymous class có thể chứa số thứ tự do compiler sinh, chẳng hạn `Outer$1Local` và `Outer$1`. Các tên này có thể thay đổi khi sửa/biên dịch lại code. Đừng lưu cứng chúng vào cấu hình; nếu cần reflection với loại class này, ưu tiên `instance.getClass()` và sử dụng `Class` hiện có.

## 4. Chương trình Java 17+ minh họa binary name

Tạo tệp **`BinaryNameDemo.java`** với nội dung đầy đủ:

```java
public class BinaryNameDemo {
    static class Nested {}

    private static void show(String label, Class<?> type) {
        System.out.println(label + ": " + type.getName());
    }

    public static void main(String[] args) throws ClassNotFoundException {
        show("Top-level", Class.forName("java.lang.String"));
        show("Member", Class.forName("java.util.Map$Entry"));
        show("Nested", Class.forName("BinaryNameDemo$Nested"));
        show("Object array", Class.forName("[Ljava.lang.String;"));
        show("Primitive array", Class.forName("[I"));

        System.out.println("Canonical: " + Nested.class.getCanonicalName());

        try {
            Class.forName("BinaryNameDemo.Nested");
        } catch (ClassNotFoundException exception) {
            System.out.println("Canonical lookup: ClassNotFoundException");
        }

        try {
            Class.forName("int");
        } catch (ClassNotFoundException exception) {
            System.out.println("Primitive lookup: ClassNotFoundException");
        }
    }
}
```

Tại thư mục chứa tệp, chạy:

```bash
javac BinaryNameDemo.java
java BinaryNameDemo
```

**Output:**

```text
Top-level: java.lang.String
Member: java.util.Map$Entry
Nested: BinaryNameDemo$Nested
Object array: [Ljava.lang.String;
Primitive array: [I
Canonical: BinaryNameDemo.Nested
Canonical lookup: ClassNotFoundException
Primitive lookup: ClassNotFoundException
```

Ở đây `BinaryNameDemo.Nested` là canonical name có ích trong source Java, còn `BinaryNameDemo$Nested` là binary name để tìm lớp. Vì chương trình không khai báo package, phần đầu binary name chỉ là `BinaryNameDemo`. Nếu file nằm trong `package demo;`, chuỗi tra cứu sẽ là `demo.BinaryNameDemo$Nested`.

Ví dụ cũng minh họa `Class.forName` **không tự biến** tên array trong mã nguồn `String[]` thành dạng JVM và **không tự biến** chuỗi `int` thành primitive `Class`.

## 5. Nạp kiểu bằng tên và thời điểm khởi tạo

`Class.forName(String)` tìm theo tên và **yêu cầu khởi tạo** lớp đích khi cần. `Class.forName(name, false, loader)` vẫn nạp/liên kết lớp nhưng **không chủ động khởi tạo** nó; `ClassLoader.loadClass(name)` thông thường cũng chưa yêu cầu khởi tạo. Đây là các thao tác khác với gọi constructor để tạo instance.

| Lời gọi | Kết quả cần lưu ý |
| --- | --- |
| `Class.forName("demo.Widget")` | Tìm theo tên và yêu cầu chạy static initialization của `Widget` nếu chưa diễn ra. |
| `Class.forName("demo.Widget", false, loader)` | Lấy metadata để khám phá kiểu trước khi chủ động sử dụng. |
| `Class.forName("[Ldemo.Widget;")` | Tìm kiểu mảng; không vì thế mà tự khởi tạo lớp phần tử `Widget`. |

Tên đúng vẫn có thể không tìm được nếu loader không thấy định nghĩa. Lớp tìm thấy cũng có thể lỗi khi liên kết hoặc khởi tạo. Bài về overload ba đối số đi sâu vào việc chọn loader và cờ `initialize`; bài về vòng đời lớp phân tích riêng các thời điểm JVM chạy `static`.

## 6. Tìm được `Class` chưa phải đã có đối tượng

`Class.forName` chỉ trả về metadata của kiểu, không tự tạo instance. Khi muốn khởi tạo đối tượng bằng reflection, cần tìm constructor phù hợp:

```java
Class<?> type = Class.forName("java.util.ArrayList");
Object instance = type.getDeclaredConstructor().newInstance();
System.out.println(instance.getClass().getName());
```

Đây là **fragment** đặt trong phương thức đã xử lý/khai báo `ReflectiveOperationException`; output là `java.util.ArrayList`. `ArrayList` có constructor không tham số; không phải lớp nào cũng có. Một constructor có thể không public hoặc bị hạn chế truy cập bởi module system; `getDeclaredConstructor().newInstance()` không bảo đảm thành công cho mọi kiểu vừa nạp.

Với kiểu biết sẵn lúc biên dịch, `SomeType.class` thường ngắn gọn và an toàn kiểu hơn; `Class.forName` phù hợp khi tên kiểu đến từ cấu hình hoặc cơ chế plugin, framework hay lập trình động.

## 7. Chẩn đoán lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException` với `java.util.Map.Entry` | Nhầm canonical name với binary name | Dùng `java.util.Map$Entry`. |
| `ClassNotFoundException` với `String` | Thiếu tên package | Dùng `java.lang.String`. |
| `ClassNotFoundException` với `java.lang.String[]` | Nhầm cách viết array trong source | Dùng `[Ljava.lang.String;` hoặc `String[].class`. |
| `ClassNotFoundException` với `int` | Primitive không được loader tìm như class | Dùng `int.class`. |
| Tên đúng vẫn không tìm thấy | Sai classpath, module path hoặc class loader | Kiểm tra dependency runtime và loader. |
| `ExceptionInInitializerError` | Static initialization thất bại | Xem nguyên nhân gốc trong static initializer. |
| `NoClassDefFoundError` | Lớp/dependency cần khi liên kết hoặc sử dụng bị thiếu, hoặc lớp từng khởi tạo thất bại | Xem lỗi đầu tiên trong log và chuỗi nguyên nhân. |
| `LinkageError` khác | Lỗi xác minh/liên kết hoặc bytecode không tương thích | Kiểm tra dependency và phiên bản thư viện. |

`ClassNotFoundException` là **checked exception**, thường liên quan tới tra cứu lớp theo tên. `ExceptionInInitializerError`, `NoClassDefFoundError` là các **Error**, không được xử lý chỉ bằng `catch (ClassNotFoundException)`. Tránh bắt `Error` một cách đại trà để che lỗi triển khai/môi trường.

## 8. Áp dụng an toàn với tên lớp động

Khi đọc tên class từ cấu hình, hãy lưu binary name chính xác nếu có thể, ví dụ dùng `Plugin.class.getName()` ở nơi tạo dữ liệu. Không tự chuyển toàn bộ `.` thành `$`, vì dấu chấm trong package phải giữ nguyên. Nếu cần class loader riêng (plugin hoặc application server), dùng overload ba tham số và giữ đúng loader của plugin.

Việc nạp và khởi tạo lớp có thể thực thi mã trong static initializer. Nếu tên đến từ dữ liệu bên ngoài, cần giới hạn lớp cho phép, kiểm tra kiểu cha/interface dự kiến và chỉ tạo instance theo hợp đồng rõ ràng. Chẳng hạn, sau khi xác định `binaryName` đã được phép:

```java
Class<?> loaded = Class.forName(binaryName, false, pluginClassLoader);
if (!Runnable.class.isAssignableFrom(loaded)) {
    throw new IllegalArgumentException("Expected Runnable");
}
Class<? extends Runnable> taskType = loaded.asSubclass(Runnable.class);
```

Đây là **fragment** dùng hai biến có sẵn `String binaryName` và `ClassLoader pluginClassLoader`; nó mới kiểm tra subtype, chưa tạo instance. Dù đã dùng `initialize=false`, việc thao tác tiếp theo với class có thể làm JVM khởi tạo nó. Chỉ kiểm tra subtype không thay thế danh sách class được phép và đánh giá mức độ tin cậy của nguồn.

## 9. Câu hỏi tự kiểm tra

1. Source có `package demo;` và `Outer` chứa `static class Inner`. Chuỗi nào để tra cứu inner type? **`"demo.Outer$Inner"`**, không phải `"demo.Outer.Inner"`.
2. Để tìm `String[][]`, dùng tên nào? **`"[[Ljava.lang.String;"`**: hai dấu `[` cho hai chiều, `Ljava.lang.String;` cho thành phần reference type.
3. Vì sao `Class.forName("int")` không thay `int.class`? **Primitive không phải lớp được loader định nghĩa theo binary name**.
4. Muốn lấy `Class` mà chưa yêu cầu chạy static initializer, dùng gì? **`Class.forName(binaryName, false, loader)`**, đồng thời hiểu các thao tác về sau có thể khởi tạo lớp.
5. Tại sao tên đúng vẫn tìm thất bại? **Class loader hoặc classpath/module path runtime không chứa/không nhìn thấy class phù hợp**.

**Ghi nhớ:** Đối với lớp/interface thông thường, dùng **binary name**; với member type sử dụng dấu `$`. Đối với mảng, dùng tên kiểu `[L...;` hoặc `[I`. Đối với primitive, dùng class literal. Luôn phân biệt tra cứu, khởi tạo và tạo instance để hiểu đúng hành vi của `Class.forName`.