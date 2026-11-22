# Chuyển tên lớp Java thành đường dẫn tài nguyên `.class`

Trong Java, khi biết **tên nhị phân (binary name)** của một lớp hoặc interface, ta thường có thể suy ra **tên tài nguyên tương đối** của tệp bytecode bằng quy tắc:

```text
tên nhị phân:  com.example.service.UserService
tên tài nguyên: com/example/service/UserService.class
```

Công thức cốt lõi là **thay mỗi dấu chấm (`.`) phân tách package bằng dấu gạch chéo xuôi (`/`), rồi nối `.class`**. Đây là quy ước đặt tệp class trong thư mục hoặc JAR; kết quả là *tên tài nguyên* dùng cho các API lookup, không phải đường dẫn hệ điều hành tuyệt đối và cũng không chứng minh tài nguyên thực sự tồn tại.

## 1. Hiểu đúng các loại tên

- **Tên nhị phân (binary name):** tên dùng để định danh lớp khi nạp qua các API như `ClassLoader.loadClass(String)`; ví dụ `com.example.Outer$Inner`. Lấy từ `clazz.getName()` đối với một lớp/interface có tên thông thường.
- **Tên nội bộ JVM (internal name):** dùng `/` giữa các thành phần package, chẳng hạn `com/example/Outer$Inner`. Nó xuất hiện trong mô tả bytecode/class file và gần với phần tên tài nguyên trước hậu tố `.class`.
- **Tên tài nguyên class:** tên nội bộ tương ứng cộng `.class`, ví dụ `com/example/Outer$Inner.class`. Các API tài nguyên thông thường dùng dấu `/` trên mọi hệ điều hành.
- **Tên canonical:** `clazz.getCanonicalName()` thường cho tên dễ đọc trong mã Java, ví dụ `com.example.Outer.Inner`. Dùng chuỗi này để thay `.` sẽ *sai* đối với lớp lồng nhau, vì nó sẽ tạo ra `Outer/Inner.class` thay cho `Outer$Inner.class`.
- **Tên đơn giản:** `clazz.getSimpleName()` trả về `Inner` hoặc `UserService`, nhưng thiếu package và tên lớp bao ngoài; không đủ để suy ra đường dẫn đầy đủ.

Ví dụ đối chiếu:

| Loại | Tên nhị phân | Đường dẫn tài nguyên thường gặp |
|---|---|---|
| Lớp top-level trong package | `org.acme.App` | `org/acme/App.class` |
| Lớp top-level ở package mặc định | `App` | `App.class` |
| Lớp thành viên static hoặc non-static | `org.acme.Outer$Inner` | `org/acme/Outer$Inner.class` |
| Interface | `org.acme.Task` | `org/acme/Task.class` |
| Lớp anonymous do trình biên dịch đặt tên | Ví dụ `org.acme.Outer$1` | Ví dụ `org/acme/Outer$1.class` |

Tên của lớp local/anonymous phụ thuộc cấu trúc chương trình và trình biên dịch; hãy lấy trực tiếp từ `Class.getName()` nếu cần thay vì tự đoán chỉ số `$1`, `$2`.

## 2. Quy tắc chuyển đổi

Với một **binary name hợp lệ của lớp/interface có tên**, phép chuyển đổi thông dụng là:

```java
String resourcePath = binaryName.replace('.', '/') + ".class";
```

Các bước có ý nghĩa rõ ràng:

1. Bắt đầu với binary name, ví dụ `com.acme.Outer$Worker`.
2. Đổi dấu `.` ngăn cách package thành `/`: `com/acme/Outer$Worker`.
3. **Giữ nguyên ký tự `$`** trong tên nhị phân của lớp lồng nhau; `$` là một phần tên tệp đã được biên dịch.
4. Nối chính xác hậu tố `.class`: `com/acme/Outer$Worker.class`.

Không dùng `File.separator` để thay `/`: tên tài nguyên Java có quy ước dùng dấu `/` ngay cả trên Windows. Không dùng `replace(".", File.separator)` hoặc `Path.of(...)` nếu đích là tham số `ClassLoader.getResource`. Khi cần truy cập tệp vật lý trên file system, hãy xử lý riêng việc ánh xạ thư mục, URL và đường dẫn tương ứng.

Điều kiện quan trọng: nếu chuỗi đầu vào vốn đã là `com/acme/Foo.class` thì **không** áp dụng thêm công thức. Phải xác định đầu vào là *binary name*, không phải đường dẫn tài nguyên, tên canonical hoặc chuỗi hiển thị tùy ý.

## 3. Ví dụ Java 17+ chạy được

Lưu nguồn vào `src/demo/path/ResourcePathDemo.java` (tạo trước các thư mục cần thiết):

```java
package demo.path;

public class ResourcePathDemo {
    static class Nested {
    }

    static String classFilePath(Class<?> type) {
        if (type.isPrimitive() || type.isArray()) {
            throw new IllegalArgumentException(
                    "Primitive and array types have no own .class resource");
        }
        return type.getName().replace('.', '/') + ".class";
    }

    public static void main(String[] args) {
        Class<?> type = Nested.class;
        String path = classFilePath(type);
        ClassLoader loader = type.getClassLoader();

        System.out.println("Binary name: " + type.getName());
        System.out.println("Canonical name: " + type.getCanonicalName());
        System.out.println("Resource path: " + path);
        System.out.println("Via loader: " + (loader.getResource(path) != null));
        System.out.println("Via class absolute: "
                + (type.getResource("/" + path) != null));
        System.out.println("Via class relative: "
                + (type.getResource("ResourcePathDemo$Nested.class") != null));
    }
}
```

Biên dịch và chạy từ thư mục chứa `src`:

```bash
javac -d out src/demo/path/ResourcePathDemo.java
java -cp out demo.path.ResourcePathDemo
```

Kết quả khi chạy với các class vừa biên dịch trên classpath `out`:

```text
Binary name: demo.path.ResourcePathDemo$Nested
Canonical name: demo.path.ResourcePathDemo.Nested
Resource path: demo/path/ResourcePathDemo$Nested.class
Via loader: true
Via class absolute: true
Via class relative: true
```

`javac -d out` đặt `ResourcePathDemo.class` và `ResourcePathDemo$Nested.class` vào thư mục `out/demo/path/`. Lệnh `java -cp out` đưa thư mục `out` lên classpath, do đó tài nguyên được tìm thấy. Nếu bạn thay đổi classpath, đóng gói vào JAR/module hoặc sử dụng bộ nạp lớp đặc biệt, trạng thái tìm được tài nguyên có thể khác.

Trong hàm `classFilePath`, sử dụng `Class<?>` giúp lấy trực tiếp binary name của lớp đang xét, tránh nhầm với tên canonical. Hàm chủ động từ chối kiểu nguyên thủy và kiểu mảng vì chúng không có tệp `.class` độc lập tương ứng với chính kiểu đó. Với các loại lớp sinh động/hidden, đường dẫn xây được vẫn chưa đảm bảo có tài nguyên để đọc.

## 4. Tra cứu tài nguyên: `ClassLoader` và `Class`

Hai kiểu lookup dưới đây có quy tắc tên đầu vào khác nhau:

| API | Đầu vào | Cách hiểu |
|---|---|---|
| `loader.getResource("demo/path/ResourcePathDemo.class")` | Không có `/` đầu | Tên tài nguyên tính từ **gốc lookup của class loader** |
| `loader.getResourceAsStream("demo/path/ResourcePathDemo.class")` | Không có `/` đầu | Tìm tài nguyên và mở stream để đọc byte |
| `ResourcePathDemo.class.getResource("/demo/path/ResourcePathDemo.class")` | Có `/` đầu | Tên tuyệt đối từ gốc tài nguyên theo API của `Class` |
| `ResourcePathDemo.class.getResource("ResourcePathDemo.class")` | Không có `/` đầu | Tên tương đối so với package `demo.path` |
| `ResourcePathDemo.class.getResourceAsStream("ResourcePathDemo.class")` | Không có `/` đầu | Mở stream tương đối so với package |

Đối với ví dụ trên, gọi `type.getResource("demo/path/ResourcePathDemo$Nested.class")` sẽ tìm tương đối trong `demo/path/`, tức thực chất tìm đường dẫn bắt đầu bằng `demo/path/demo/path/...`, nên thường trả `null`. Nếu đã có đường dẫn đầy đủ, thêm `/` phía trước khi gọi `Class.getResource(...)`; **không** thêm `/` khi gọi `ClassLoader.getResource(...)`.

Các API `getResource` trả `URL` hoặc `null`, còn `getResourceAsStream` trả `InputStream` hoặc `null`. Với stream, phải đóng bằng try-with-resources. URL có thể là `file:`, `jar:`, `jrt:` hoặc dạng do loader cung cấp; không ép mọi URL thành `Path` trên đĩa.

```java
String path = MyType.class.getName().replace('.', '/') + ".class";
try (java.io.InputStream input =
             MyType.class.getResourceAsStream("/" + path)) {
    if (input == null) {
        throw new java.io.FileNotFoundException(path);
    }
    byte[] bytes = input.readAllBytes(); // Java 9+
    System.out.println("Read " + bytes.length + " bytes");
}
```

Đây là **đoạn minh họa dùng trong một phương thức có xử lý/khai báo `IOException` và có lớp `MyType`**, không phải tệp Java độc lập. Số byte phụ thuộc bản biên dịch nên không có stdout cố định. Cách gọi qua `MyType.class` còn tiện khi class loader của lớp là bootstrap loader: `MyType.class.getClassLoader()` có thể trả `null`, còn `MyType.class.getResource(...)` vẫn là API hợp lệ để tra cứu tài nguyên của lớp.

## 5. Phân biệt việc tạo tên, tìm tài nguyên và nạp lớp

Ba thao tác này khác nhau:

```text
Binary name
    |
    | replace('.', '/') + ".class"
    v
Resource name              (biến đổi chuỗi, chưa có I/O)
    |
    | getResource / getResourceAsStream
    v
URL / InputStream / null   (tìm hoặc đọc tài nguyên)
    
ClassLoader.loadClass(binaryName)
    |
    v
Class<?>                   (cơ chế nạp/định nghĩa lớp)
```

- `ClassLoader.loadClass("demo.path.ResourcePathDemo")` nhận **binary name** có dấu `.`; truyền `demo/path/ResourcePathDemo.class` vào API này là sai loại đầu vào.
- Chuyển tên chỉ là xử lý văn bản. Nó không gọi `loadClass`, không mở JAR, không đọc bytecode và không khởi tạo lớp.
- Nếu đã có đối tượng `Class<?>`, lớp tương ứng đã được định nghĩa trong JVM, nhưng điều đó không có nghĩa ta đọc được tài nguyên `.class` ban đầu.
- Nếu `getResource(path) != null`, ta mới biết lookup tìm thấy một tài nguyên ứng với tên đó. Chỉ riêng việc tìm thấy tài nguyên chưa chứng minh JVM đang chạy đúng những byte từ tài nguyên này.

Từ góc độ class loader, một tên lớp có thể được giải quyết qua delegation, module, JAR, thư mục, hoặc bytecode định nghĩa trực tiếp từ mảng byte. `findClass` của custom loader có thể dùng quy tắc đường dẫn này để tìm bytecode, nhưng có thể chọn chiến lược khác. Vì thế **quy tắc đặt tên là quy ước thông dụng, không phải cam kết tồn tại tài nguyên**.

## 6. Các trường hợp dễ nhầm

### 6.1. Sai đường dẫn do dùng canonical name

Nếu lấy `sample.Outer.Inner` rồi chạy `replace('.', '/') + ".class"`, chương trình sẽ tìm nhầm `sample/Outer/Inner.class` và thường nhận `null`. Resource đúng của member `Inner` là `sample/Outer$Inner.class`; hãy lấy từ `Outer.Inner.class.getName()` hoặc binary name thực tế. Đây là lỗi chọn đầu vào, không chứng minh ClassLoader không hỗ trợ lớp lồng nhau.

### 6.2. Kiểu nguyên thủy, mảng và descriptor

- `int.class.getName()` trả `int`, nhưng không có tài nguyên lớp riêng `int.class`.
- `String[].class.getName()` trả `[Ljava.lang.String;`; đây là cú pháp tên kiểu mảng của JVM, không thể biến `.` thành `/` rồi thêm `.class` để tìm class file của chính mảng.
- `int[].class.getName()` trả `[I`. JVM tạo kiểu mảng trong runtime; nó không tương ứng với `[I.class` trong JAR.

Nếu muốn class file của **kiểu thành phần** của mảng đối tượng, cần lấy `getComponentType()` (có thể nhiều lần với mảng đa chiều), rồi xét trường hợp component đó có tên và tài nguyên hay không. Không coi mảng là lớp có tệp bytecode riêng.

### 6.3. Lớp local, anonymous, hidden hoặc sinh trong runtime

Lớp local/anonymous thường có tên nhị phân chứa `$` cùng thành phần do compiler sinh, nhưng không nên tự tổng hợp tên. Hidden class và các lớp được custom loader định nghĩa từ byte có thể không có tài nguyên class tương ứng, dù tồn tại một đối tượng `Class<?>`. Với một số hidden class, `Class.getName()` còn chứa hậu tố đặc thù không phải binary name thông thường. Tránh giả định mọi `Class<?>` đều chuyển ngược thành một URL `.class`.

### 6.4. Classpath, JAR và Java Platform Module System

Khi biên dịch lớp `pkg.Example` vào `out`, đường dẫn vật lý thường là `out/pkg/Example.class`, còn tên resource vẫn chỉ là `pkg/Example.class`. Trong JAR, đó là **tên entry** như `pkg/Example.class`. Với multi-release JAR, loader/runtime có thể chọn phiên bản class khác nhau theo phiên bản Java; đừng giả định entry đang thấy trong archive đồng nhất với bytecode đã nạp.

Khi chạy với **named modules** (JPMS), việc tìm tài nguyên còn phụ thuộc module và cách loader thực hiện lookup; tài nguyên có thể không truy cập được qua cách gọi hiện tại. Không suy ra chắc chắn một file thiếu chỉ từ kết quả `null` nếu chưa xác minh module, loader và lookup path.

### 6.5. Tên không tin cậy

Nếu đầu vào là chuỗi bên ngoài như đường dẫn người dùng nhập, `replace('.', '/') + ".class"` **không** thay thế việc xác thực. Cần phân biệt binary name với path, áp dụng danh sách package/class được phép và tránh dùng đường dẫn nhận từ người dùng để tự động đọc, định nghĩa hoặc thực thi lớp. Truyền `Class<?>` đã được lựa chọn rõ ràng an toàn hơn việc ghép tùy ý một tên từ chuỗi lạ.

## 7. Checklist xử lý sự cố

Khi code không tìm được `.class`, kiểm tra theo thứ tự:

1. **Đầu vào có phải binary name không?** Dùng `type.getName()`; tránh `getCanonicalName()` với nested class.
2. **Dấu phân tách đúng chưa?** Chỉ đổi `.` của package thành `/`; giữ `$`; có đúng một hậu tố `.class`.
3. **Đang gọi API nào?** `ClassLoader.getResource` không dùng `/` đầu; `Class.getResource` dùng `/` đầu nếu muốn tên tuyệt đối.
4. **Classpath/module path và loader nào?** Xác nhận lớp/tài nguyên thực sự nằm trong thư mục, JAR hoặc module mà loader đang sử dụng.
5. **Đây có phải primitive, array, hidden hoặc generated class không?** Những kiểu đó có thể không có tệp tài nguyên độc lập.
6. **Có kiểm tra `null` và đóng stream không?** Lookup không thành công là tình huống hợp lệ; đừng gọi `openStream` hoặc `readAllBytes` khi chưa kiểm tra.

**Ghi nhớ:** Với lớp hoặc interface thông thường, `type.getName().replace('.', '/') + ".class"` là công thức suy ra **tên resource của bytecode theo quy ước**. Dùng đường dẫn này với API tra cứu phù hợp, đồng thời tách bạch việc hình thành tên với việc tài nguyên tồn tại hoặc bytecode đang chạy đến từ đâu.
