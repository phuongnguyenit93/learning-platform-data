# Định danh lớp bằng tên nhị phân kết hợp bộ nạp định nghĩa trong JVM

## 1. Ý tưởng trung tâm: tên giống nhau chưa chắc cùng một kiểu

Trong Java source, khi nhìn thấy `com.example.Service`, chúng ta thường nghĩ đây là một lớp duy nhất. Nhưng JVM có thể chạy nhiều ứng dụng, plugin, module hoặc môi trường cách ly, mỗi môi trường có cách nạp các class file riêng. Vì vậy JVM không thể nhận diện một **class/interface runtime** chỉ bằng chuỗi tên.

Theo **Java Virtual Machine Specification (JVMS §5.3)**, một class hoặc interface tại thời điểm chạy được xác định bởi **cặp**:

> **(Tên nhị phân — binary name, bộ nạp định nghĩa — defining class loader)**

Có thể ký hiệu:

```text
Runtime type identity = (N, Ld)

N  = binary name của class/interface
Ld = defining class loader đã định nghĩa class/interface ấy
```

Hệ quả cực kỳ quan trọng:

- **Cùng binary name + cùng defining loader** → cùng class/interface runtime được đại diện bởi cùng một đối tượng `Class` trong một JVM, theo những quy tắc class loading hợp lệ.
- **Cùng binary name + defining loader khác** → có thể là **hai class/interface runtime khác nhau**, dù bytecode `.class` được đọc từ cùng một tệp và các khai báo nguồn hoàn toàn giống nhau.
- **Binary name khác** → là hai định danh class/interface khác nhau, dù có dùng cùng một loader.
- Việc một loader **yêu cầu nạp** một class không nhất thiết nghĩa là chính loader đó đã **định nghĩa** class, vì yêu cầu có thể được **ủy quyền (delegation)** cho loader khác.

Ví dụ logic:

```text
("com.example.Plugin", loader A) ≠ ("com.example.Plugin", loader B)

("com.example.Plugin", loader A) = ("com.example.Plugin", loader A)
```

Đây là **định danh kiểu** trong JVM, không phải phép so sánh chuỗi, không phải `equals()` của các instance, và không phụ thuộc việc hai tệp class có nội dung giống hệt nhau hay không.

**Mục tiêu học tập:** phân biệt binary name với các dạng tên khác, defining loader với initiating loader, giải thích ClassCastException “lớp X không thể cast về lớp X”, biết cách cô lập plugin và chia sẻ API đúng cách, hiểu ảnh hưởng tới package, array types, reflection và chẩn đoán class loading.

## 2. Binary name chính xác là gì?

**Binary name** là tên của class/interface theo quy tắc Java dùng trong class file và liên kết nhị phân, không phải mọi cách hiển thị tên thân thiện của Java source. Với top-level class, tên thường gồm tên package và tên class nối bằng dấu chấm:

```java
package com.example;
public class Account { }
```

Binary name: `com.example.Account`.

Với member class lồng nhau:

```java
package com.example;

public class Outer {
    public static class Inner { }
}
```

Binary name của member class: **`com.example.Outer$Inner`**. Trong Java source, chúng ta thường viết `Outer.Inner`; dấu `$` trong binary name phản ánh quy tắc tên nhị phân, không phải một package mới.

### 2.1. Các dạng tên cần phân biệt

| Dạng tên | Ví dụ | Dùng trong hoàn cảnh |
| --- | --- | --- |
| Source/canonical name | `com.example.Outer.Inner` | Cú pháp tên kiểu dễ đọc trong Java source; `Class.getCanonicalName()` khi có canonical name |
| **Binary name** | `com.example.Outer$Inner` | Nạp class theo tên, định danh runtime của nonarray class/interface |
| Internal form trong class file | `com/example/Outer$Inner` | Cấu trúc constant pool và nhiều descriptor JVM |
| Đường dẫn class resource | `com/example/Outer$Inner.class` | Tìm bytecode class theo quy ước resource của classpath/JAR |
| Reference field descriptor | `Lcom/example/Outer$Inner;` | Descriptor kiểu reference trong JVM |
| Array class name | `[Lcom.example.Outer$Inner;` | Dạng `Class.getName()` của mảng reference |

**Không gõ `com.example.Outer.Inner` vào `ClassLoader.loadClass` khi đang muốn member class `Outer.Inner`** nếu binary name của nó là `com.example.Outer$Inner`. Đối với `Class.forName` và `ClassLoader.loadClass`, hãy dùng dạng tên phù hợp với hợp đồng API.

Một số class cục bộ (local) và anonymous class có binary name do compiler tạo theo quy tắc liên quan số thứ tự và dấu `$`. Đừng xây API dựa trên giả định mọi tên dạng `$1` sẽ ổn định khi đổi mã nguồn hoặc phiên bản compiler.

### 2.2. Đừng lấy tên file thay cho định danh runtime

Một tệp `Plugin.class` không có nghĩa nó là một class tên `Plugin` trong default package. Binary name có thể là `com.example.Plugin`, và class loader phải tìm/định nghĩa class đúng tên mà JVM kỳ vọng. Nếu dùng `defineClass(name, bytes,...)` mà tên truyền vào không khớp binary name được khai báo trong bytecode, có thể xảy ra lỗi liên quan tên/định dạng class.

Tương tự, **cùng binary name không chứng minh cùng class**: loader cũng là một phần của định danh.

## 3. Defining loader và initiating loader: hai vai trò khác nhau

Một class loader có thể:

1. **Tự đọc bytecode rồi định nghĩa class**, thông qua các cơ chế như `defineClass`.
2. **Ủy quyền cho loader khác** để tìm và định nghĩa class.
3. Tham gia chuỗi yêu cầu nạp mà class thực tế cuối cùng được định nghĩa bởi một loader khác.

JVMS dùng hai khái niệm:

- **Defining class loader (`Ld`):** loader trực tiếp định nghĩa class/interface runtime từ biểu diễn nhị phân phù hợp, hoặc loader mà đặc tả gắn với định nghĩa array class theo quy tắc riêng.
- **Initiating class loader (`Li`):** loader bắt đầu/khởi xướng một hoạt động loading cho tên class/interface và được JVM ghi nhận theo các quy tắc loading, kể cả khi việc định nghĩa được ủy quyền cho loader khác.

Một class có **một defining loader** nhưng có thể có **nhiều initiating loaders**.

### 3.1. Ví dụ delegation

```text
Caller yêu cầu loader PluginLoader nạp java.lang.String
                       |
                       v
                PluginLoader
                       |
                  delegate
                       v
               Parent / Platform ...
                       |
                       v
                Bootstrap loader
                       |
                       v
             định nghĩa java.lang.String
```

Khi yêu cầu thành công, `PluginLoader` đã tham gia **initiating loading**, nhưng **bootstrap loader** mới là defining loader của `java.lang.String`. Nếu cùng `PluginLoader` yêu cầu lại `java.lang.String`, việc nạp không tạo ra một class String mới của PluginLoader.

**Đừng lấy loader được truyền vào `loadClass` hoặc `Class.forName` rồi mặc định đó là defining loader**. Loader ấy có thể ủy quyền.

### 3.2. `Class.getClassLoader()` trả về gì?

Với một nonarray class thông thường, `Class.getClassLoader()` cung cấp **defining class loader** của class đó. Nếu class được định nghĩa bởi bootstrap loader, API thông thường trả về **`null`** để biểu thị bootstrap (không phải “class chưa được nạp”).

```java
System.out.println(String.class.getClassLoader() == null); // true trên JDK chuẩn
```

Dòng trên là ví dụ quan sát bootstrap definition của `String` trên JDK phổ biến. Không so sánh mọi loader bằng tên in ra từ `toString()`; để biết có phải cùng loader object, kiểm tra identity của đối tượng loader.

### 3.3. Parent-first là quy ước của loader thường dùng, không phải định nghĩa của class identity

`ClassLoader.loadClass` mặc định dùng mô hình ưu tiên ủy quyền cho parent (*parent-first delegation*) đối với những class phù hợp. Điều này giúp ứng dụng sử dụng chung các lớp nền tảng Java và tránh tạo nhiều bản không cần thiết.

Nhưng **parent-first không phải một định luật bắt buộc cho mọi custom loader**. Có các thiết kế child-first hoặc chọn lọc theo tên để cô lập plugin. Dù chiến lược nạp nào được dùng, JVM vẫn xác định class runtime theo **binary name và defining loader thực tế**.

Không nên tùy tiện nạp lại các lớp nền tảng hoặc class thuộc package `java.*` bằng loader tùy biến; Java có các ràng buộc bảo vệ package, liên kết kiểu và bảo mật. Thí nghiệm bên dưới **chỉ tự định nghĩa lại một lớp do ứng dụng sở hữu**, còn các lớp nền tảng được ủy quyền.

## 4. Ví dụ trực quan: hai loader định nghĩa cùng bytecode

Xét một class file có binary name `com.example.Plugin`.

```text
                      Plugin.class (cùng bytecode)
                               |
             +-----------------+-----------------+
             |                                   |
        ByteArrayLoader A                    ByteArrayLoader B
             |                                   |
       defineClass(...)                    defineClass(...)
             |                                   |
             v                                   v
    Class A: (Plugin, A)                 Class B: (Plugin, B)
             |                                   |
             +-----------------X-----------------+
                      Không cùng kiểu runtime
```

Hai bản có thể:

- Có cùng `Class.getName()` là `com.example.Plugin`.
- Có cùng method signatures, field names và bytecode.
- Vẫn **khác `Class` object**: `classA == classB` là false.
- Không thể ép một instance `classA` sang `classB` bằng cast thông thường chỉ vì tên giống nhau.
- Có thể gây `ClassCastException` lúc runtime, hoặc lỗi liên kết khác khi các kiểu của hai loader xung đột.

Đặc điểm này được dùng trong plugin isolation, application servers, hot deployment, test runners và các hệ thống cho phép nhiều phiên bản thư viện cùng tồn tại.

**Tách biệt không đồng nghĩa an toàn tuyệt đối:** các loader vẫn sống trong cùng một tiến trình JVM và có thể truy cập tài nguyên dùng chung nếu API, quyền và cơ chế bảo vệ cho phép. ClassLoader là công cụ tách **namespace/type identity**, không tự tạo sandbox bảo mật hoàn chỉnh.

## 5. Thí nghiệm Java 17+ hoàn chỉnh: cùng tên, khác defining loader

Ví dụ này dùng **một tệp nguồn** để dễ chạy. Chúng ta sẽ dùng hai instance custom `ClassLoader` đọc **cùng một tệp class của nested class**, sau đó gọi `defineClass` riêng trong mỗi loader. Cả hai loader vẫn ủy quyền các class khác cho parent, để không gây xung đột với `java.lang.*`.

Tạo tệp **`ClassIdentityDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Array;

public class ClassIdentityDemo {
    public static class Payload {
        public Payload() {}

        public String say() {
            return "payload";
        }
    }

    static final class SelectiveLoader extends ClassLoader {
        private final String target;

        SelectiveLoader(ClassLoader parent, String target) {
            super(parent);
            this.target = target;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);

                if (result == null) {
                    if (name.equals(target)) {
                        String resource = name.replace('.', '/') + ".class";

                        try (InputStream in =
                                getParent().getResourceAsStream(resource)) {
                            if (in == null) {
                                throw new ClassNotFoundException(name);
                            }

                            byte[] bytes = in.readAllBytes();
                            result = defineClass(name, bytes, 0, bytes.length);
                        } catch (IOException e) {
                            throw new ClassNotFoundException(name, e);
                        }
                    } else {
                        result = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String binaryName = Payload.class.getName();
        ClassLoader parent = ClassIdentityDemo.class.getClassLoader();

        SelectiveLoader one = new SelectiveLoader(parent, binaryName);
        SelectiveLoader two = new SelectiveLoader(parent, binaryName);

        Class<?> first = one.loadClass(binaryName);
        Class<?> second = two.loadClass(binaryName);
        Object value = first.getDeclaredConstructor().newInstance();

        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("same Class object: " + (first == second));
        System.out.println("loader one cache: "
                + (one.loadClass(binaryName) == first));
        System.out.println("defining loader one: "
                + (first.getClassLoader() == one));
        System.out.println("defining loader two: "
                + (second.getClassLoader() == two));

        System.out.println("first.isInstance(value): "
                + first.isInstance(value));
        System.out.println("second.isInstance(value): "
                + second.isInstance(value));
        System.out.println("app Payload.isInstance(value): "
                + Payload.class.isInstance(value));

        System.out.println("shared String by delegation: "
                + (one.loadClass("java.lang.String")
                    == two.loadClass("java.lang.String")));

        Class<?> arrayOne = Array.newInstance(first, 0).getClass();
        Class<?> arrayTwo = Array.newInstance(second, 0).getClass();

        System.out.println("array binary names equal: "
                + arrayOne.getName().equals(arrayTwo.getName()));
        System.out.println("array runtime types equal: "
                + (arrayOne == arrayTwo));
        System.out.println("array defining loader one: "
                + (arrayOne.getClassLoader() == one));

        try {
            Payload.class.cast(value);
            System.out.println("cast succeeded");
        } catch (ClassCastException exception) {
            System.out.println("cross-loader cast: ClassCastException");
        }
    }
}
```

### 5.1. Biên dịch và chạy

Đặt tệp tại thư mục làm việc, sau đó chạy với **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 ClassIdentityDemo.java
java ClassIdentityDemo
```

Lệnh `javac` thông thường tạo các tệp class, gồm:

```text
ClassIdentityDemo.class
ClassIdentityDemo$Payload.class
ClassIdentityDemo$SelectiveLoader.class
```

Các tên nested class ở trên là binary names theo dạng dấu `$`. Đừng xóa tệp `ClassIdentityDemo$Payload.class` vì loader cần đọc resource bytes tương ứng.

### 5.2. Stdout chính xác

```text
same binary name: true
same Class object: false
loader one cache: true
defining loader one: true
defining loader two: true
first.isInstance(value): true
second.isInstance(value): false
app Payload.isInstance(value): false
shared String by delegation: true
array binary names equal: true
array runtime types equal: false
array defining loader one: true
cross-loader cast: ClassCastException
```

Các dòng trên không in PID, identity hash code hay tên implementation loader, nên kết quả **không phụ thuộc số thứ tự cấp phát của loader**. Ví dụ đã chọn chỉ một class đích để tự định nghĩa lại; những class khác vẫn đi theo delegation.

### 5.3. Giải thích cách loader hoạt động

`SelectiveLoader` ghi đè `loadClass(String, boolean)`. Với đúng tên `Payload`:

1. `getClassLoadingLock(name)` đồng bộ hoạt động nạp class theo quy tắc khóa của loader.
2. `findLoadedClass(name)` kiểm tra bản đã nạp để **không định nghĩa trùng cùng tên trong cùng loader**.
3. `getParent().getResourceAsStream(resource)` đọc các byte `Payload.class` từ classpath mà parent có thể truy cập.
4. `defineClass(name, bytes, 0, bytes.length)` tạo một **định nghĩa runtime mới** thuộc loader đang gọi.
5. `resolveClass(result)` được gọi nếu flag `resolve` yêu cầu.

Với mọi tên khác `Payload`, loader dùng `super.loadClass(name, false)`, tức cơ chế tìm class của parent. Do đó cả hai loader vẫn chia sẻ `java.lang.String` từ runtime nền tảng.

**Thí nghiệm có chủ đích chọn child-definition cho một tên duy nhất.** Đây là công cụ học tập, không phải một class loader tổng quát đủ an toàn cho mọi plugin, thư viện, module, resource và vòng đời vận hành.

### 5.4. Giải thích từng nhóm kết quả

**`same binary name: true`:** cả hai đối tượng `Class` trả cùng chuỗi tên `ClassIdentityDemo$Payload`.

**`same Class object: false`:** `first` và `second` có **defining loader khác**, nên khác class identity.

**`loader one cache: true`:** khi loader một yêu cầu lại cùng binary name, nó không định nghĩa một bản mới; `findLoadedClass` trả bản đã có.

**`defining loader one/two: true`:** `Class.getClassLoader()` trả loader object đã thực sự định nghĩa class. Hai loader khác nhau chứ không chỉ là hai chuỗi tên.

**`first.isInstance(value): true`:** `value` là object instance của class do loader một định nghĩa.

**`second.isInstance(value): false`:** dù class của loader hai có cùng tên, object không thuộc runtime class đó.

**`app Payload.isInstance(value): false`:** thậm chí `Payload.class` mà bản thân ứng dụng biết qua classpath cũng là **class thứ ba** cùng binary name nhưng do parent/app loader định nghĩa; nó không cùng class với bản do loader một tạo.

**`shared String by delegation: true`:** hai custom loader ủy quyền nạp `java.lang.String` và được cùng class chuẩn trả về.

**Hai dòng array:** array class của reference component mang identity gắn với component type và defining loader; mỗi array class ở đây cũng là một runtime class khác nhau.

**`cross-loader cast: ClassCastException`:** ép instance của loader một sang `Payload` của app loader là sai kiểu runtime. Lệnh `Class.cast` phát hiện và ném exception, chương trình bắt lại để in thông báo ổn định.

## 6. Tại sao hai class có cùng bytecode vẫn không cast được?

Java có kiểm tra kiểu ở **compile-time** và ở **runtime**. Compiler xác minh thao tác theo các kiểu mà mã đang tham chiếu, nhưng JVM khi thực thi cần biết **đối tượng thật thuộc runtime class nào**.

Ví dụ:

```text
classA = ("demo.Plugin", loaderA)
classB = ("demo.Plugin", loaderB)

Object x = new instance of classA

classA.isInstance(x) → true
classB.isInstance(x) → false
```

Không có quy tắc “nếu hai class định nghĩa cùng field/method thì JVM xem như cùng type” trong class identity. Java không áp dụng **structural typing** tự động kiểu như một số ngôn ngữ khác. Interface/superclass compatibility vẫn dựa vào các quan hệ kiểu được nạp và liên kết hợp lệ.

Trong thực tế, stack trace đôi khi gây bối rối:

```text
java.lang.ClassCastException:
  class demo.Plugin cannot be cast to class demo.Plugin
```

Đây chỉ là một **mẫu thông báo rút gọn**, không phải stdout của chương trình ví dụ. Các JVM hiện đại có thể kèm module, loader, class identity trong thông báo. Đừng kết luận runtime “nhầm lẫn”: **hai lần xuất hiện của `demo.Plugin` có thể là hai class khác nhau theo defining loader**.

### 6.1. `Class.getName()` không phải kiểm tra identity

Không nên dùng:

```java
if (a.getClass().getName().equals(b.getClass().getName())) {
    // kết luận a và b cùng runtime type
}
```

Đây là **mã minh họa có thể cho kết luận sai**. Chuỗi tên bằng nhau chỉ so sánh **một nửa** định danh. Khi muốn biết cùng runtime class chính xác, so sánh:

```java
boolean sameRuntimeClass = a.getClass() == b.getClass();
```

Nếu muốn biết một object có tương thích với kiểu được đại diện bởi `Class<?> clazz`, dùng:

```java
boolean compatible = clazz.isInstance(a);
```

Nếu `a` là null, `getClass()` gây `NullPointerException`; `clazz.isInstance(null)` trả false theo hợp đồng API. Dùng đúng phép kiểm tra theo ý nghĩa nghiệp vụ.

### 6.2. Vì sao `instanceof` cũng có thể false?

Một biểu thức như:

```java
boolean ok = value instanceof SomeType;
```

được kiểm tra theo **runtime type** và quan hệ assignability với `SomeType` mà lớp thực hiện câu lệnh đang nhìn thấy. Nếu `SomeType` qua loader khác với runtime class của `value`, kiểm tra có thể false dù `getName()` cùng tên.

## 7. Initiating loader không tự biến thành defining loader

Giả sử `L1` gọi `loadClass("java.util.List")` rồi delegation đi đến loader chuẩn `L0`. Lúc này:

```text
Yêu cầu từ L1
    |
    +→ parent/delegation
             |
             v
         L0 định nghĩa java.util.List
```

`L1` có thể được ghi nhận là **initiating loader** cho class `java.util.List`, nhưng `List.class.getClassLoader()` phản ánh defining loader thực tế, không nhất thiết là `L1`.

**Một class có thể có nhiều initiating loaders**, còn defining loader là một thành phần cố định của identity.

### 7.1. Khi nào sự phân biệt ảnh hưởng thiết kế?

- **Plugin system:** loader plugin hỏi parent về interface chung; plugin loader **khởi xướng** nạp interface nhưng **parent định nghĩa** nó, nhờ vậy host và plugin thống nhất API.
- **Web application server:** nhiều ứng dụng có loader riêng nhưng cùng dùng class Java nền tảng từ parent.
- **Dependency isolation:** plugin loader tự định nghĩa implementation/dependency nội bộ để tránh xung đột phiên bản với plugin khác.

Không yêu cầu mỗi loader tự định nghĩa mọi class nó nhìn thấy. Nếu làm vậy, nó có thể vô tình tách đôi cả các **API cần được chia sẻ**, khiến object không thể giao tiếp qua interface như dự kiến.

### 7.2. Class initialization không xác định defining loader

Khái niệm class loading/definition khác với **class initialization** (chạy `static initializer`). Một class có thể được load và link trước khi nó được khởi tạo. Điều đó không thay đổi cặp định danh đã có.

Ví dụ:

```java
Class<?> type = Class.forName("java.lang.String", false,
        ClassIdentityDemo.class.getClassLoader());
```

Đây là **đoạn mã minh họa bên trong một phương thức**, dùng overload của `Class.forName` với cờ `initialize=false`. Cờ này ảnh hưởng yêu cầu initialization, không thay đổi danh tính của class. Loader truyền vào có thể tiếp tục delegate tới defining loader khác.

## 8. Các loader tích hợp và tác động tới định danh lớp

Trên HotSpot/JDK 17 thông thường có **bootstrap** (API `getClassLoader()` thường biểu diễn bằng `null`), **platform** và **application/system** loader. Custom loader có thể tiếp tục ủy quyền hoặc tự định nghĩa bytecode; không có bảo đảm mọi loader đều dùng parent-first.

Điểm cần nhớ **riêng với class identity**: một custom loader là một **object**. Hai instance `PluginLoader` cùng Java class vẫn là hai defining loaders khác nhau nếu mỗi instance tự `defineClass` cùng binary name; còn hai loader chỉ delegate về một parent có thể cùng trả đúng một `Class<?>`. Đừng dùng tên implementation của loader thay cho phép so sánh object identity.

## 9. Array classes: ngoại lệ cần hiểu cho đúng

Đặc tả JVM phân biệt việc tạo **nonarray class/interface** và việc tạo **array class**:

- Nonarray class/interface được tạo bằng cơ chế nạp binary representation qua class loader.
- **Array class được JVM tạo trực tiếp**, không có class file `.class` thông thường tương ứng với mỗi array type.
- Với component type là **reference type**, defining loader của array class là **defining loader của component type**.
- Với component type là **primitive**, defining loader của array class là **bootstrap loader**.

Ví dụ:

```java
String[] strings = new String[2];
int[] numbers = new int[2];
```

- `String[]` là array type gắn với `java.lang.String`; trên JDK thông thường component class do bootstrap định nghĩa.
- `int[]` có primitive component `int`; array class do JVM tạo, được gắn với bootstrap loader.
- `Plugin[]` có array class gắn với defining loader của component class `Plugin`.

### 9.1. Minh họa trong chương trình đã chạy

```java
Class<?> arrayOne = Array.newInstance(first, 0).getClass();
Class<?> arrayTwo = Array.newInstance(second, 0).getClass();
```

Hai array classes này có:

- Cùng `Class.getName()` vì component classes có cùng binary name.
- **Khác `Class` object** vì component classes thuộc hai defining loaders khác nhau.
- Mỗi array class có defining loader tương ứng với component class.

Vì vậy **định danh array class cũng bị ảnh hưởng bởi component type identity**, dù array class không được định nghĩa từ một tệp `.class` riêng.

### 9.2. Tên của array class trông lạ nhưng có quy luật

Ví dụ:

| Kiểu Java | `Class.getName()` |
| --- | --- |
| `int[]` | `[I` |
| `String[]` | `[Ljava.lang.String;` |
| `String[][]` | `[[Ljava.lang.String;` |
| `Payload[]` của nested class | `[LClassIdentityDemo$Payload;` |

`Class.getName()` của array class dùng dạng bắt đầu bằng `[` theo descriptor quy định, không phải tên kiểu nguồn `java.lang.String[]`. Đừng nhầm chuỗi tên array này với đường dẫn class file. Việc nạp array type bằng API reflection có hợp đồng riêng.

## 10. Runtime package và kiểm tra quyền truy cập

Ở cấp Java source, package thường được nhìn như chuỗi tên:

```java
package com.example.plugins;
```

Nhưng tại runtime, theo JVMS, **runtime package** của nonarray class/interface được xác định bởi **package name và defining loader**.

Do đó:

```text
com.example.plugins.PluginA    do loader A định nghĩa
com.example.plugins.PluginB    do loader B định nghĩa
```

Dù hai class có cùng tên package dạng chuỗi **`com.example.plugins`**, chúng **không đương nhiên thuộc cùng runtime package**. Điều này ảnh hưởng những quyền truy cập theo package trong kiểm tra JVM, chẳng hạn package-private members và một số ràng buộc liên quan class accessibility.

**Sai lầm phổ biến:** tạo hai loader độc lập, định nghĩa hai class “cùng package” rồi kỳ vọng có thể gọi package-private method của nhau như khi chúng được nạp bằng một loader duy nhất.

### 10.1. Package trong tên không tự tạo quan hệ tin cậy

Một plugin không thể chỉ đặt class trong `com.host.internal` rồi nghiễm nhiên có mọi quyền truy cập package-private vào class của host nếu plugin class do defining loader khác tạo. Loader identity là một phần quan trọng của runtime package boundary.

Trong Java 9+ còn có **module system (JPMS)**, bổ sung các quy tắc module readability, exports và opens. Do vậy khi điều tra `IllegalAccessError` hoặc reflective access failure, có thể cần kiểm tra **cả defining loader, runtime package và module**. Không quy hết mọi lỗi truy cập cho class loader.

## 11. Shared API, isolated implementation: thiết kế plugin thực tế

Một kiến trúc plugin thường cần **cô lập implementation** nhưng **chia sẻ hợp đồng** với host:

```text
              Host / Parent loader
               định nghĩa api.Task
                       |
        +--------------+--------------+
        |                             |
   Plugin loader A                Plugin loader B
   định nghĩa impl.A              định nghĩa impl.B
   delegate api.Task              delegate api.Task
        |                             |
        +-------- thực thi qua -------+
                cùng api.Task
```

Nếu parent định nghĩa `api.Task` và cả plugin A lẫn plugin B ủy quyền nạp nó, JVM nhìn thấy **một interface runtime chung**. Các implementation có thể được dùng qua interface ở host nếu các phương thức/kiểu liên quan liên kết thành công.

Ngược lại, nếu mỗi plugin tự định nghĩa một bản `api.Task`:

```text
("api.Task", loader A) ≠ ("api.Task", loader B)
("api.Task", loader A) ≠ ("api.Task", host loader)
```

thì một object “implements api.Task” theo loader A **không tự trở thành instance của api.Task theo host**. Dù tên interface giống nhau, kiểu runtime khác nhau.

### 11.1. Ví dụ hợp đồng shared API

```java
// Ví dụ phân tách sang module/thư viện chung:
package api;

public interface Task {
    String run();
}
```

Class nguồn minh họa này **không phải chương trình độc lập**; cần đặt tại `api/Task.java` và build với một classpath/module path phù hợp. Quan trọng là package `api` và class/interface `Task` nên được **định nghĩa bởi loader được chia sẻ**, rồi implementation của từng plugin chỉ tham chiếu đến nó.

Khi API nhận/trả giá trị, cần xem cả các kiểu trong **method descriptors**. Nếu hai loader nhìn một kiểu tham số/kiểu trả về theo các class identity khác nhau, liên kết qua các loader có thể tạo lỗi hoặc mismatch.

### 11.2. Không biến mọi thư viện thành shared dependency

Cô lập dependency riêng có thể có ích nếu hai plugin cần hai phiên bản thư viện không tương thích. Nhưng nếu library type xuất hiện trong **chữ ký API giao tiếp qua boundary**, các bên phải có thiết kế thống nhất kiểu. Những kiểu dùng chung trong interface là điểm quan trọng để xác định **nên delegate** hay **nên isolate**.

Một quy tắc thực hành:

- **Share** các API contract, DTO công khai hoặc class dùng để trao đổi qua boundary khi muốn type identity thống nhất.
- **Isolate** implementation/internal dependency không cần trao đổi trực tiếp nếu có lý do về phiên bản hoặc lifecycle.
- Thiết kế cơ chế serialization/message passing khi muốn giao tiếp giữa những vùng có namespace khác nhau mà không thể chia sẻ cùng kiểu runtime.

Đừng áp dụng “child-first toàn bộ mọi package” chỉ để giải quyết một trùng tên dependency rồi tạo ra lỗi cast cho interface chung.

## 12. Loading constraints và an toàn kiểu khi liên kết

JVMS §5.3.4 quy định **loading constraints** để bảo đảm tính an toàn kiểu khi các class từ những defining loaders khác nhau có symbolic references tới trường/phương thức mà kiểu xuất hiện trong descriptor.

Ví dụ khái niệm:

```text
Host method:    api.Result process(api.Request request)
Plugin method:  api.Result process(api.Request request)
```

Nếu host và plugin cần liên kết một quan hệ phương thức/kiểu qua boundary, runtime không được tùy tiện xem hai `api.Request` là tương đương khi chúng thực chất được định nghĩa bởi hai loaders khác nhau.

Do đó:

- Một số mismatch đơn giản được thấy dưới dạng `ClassCastException` hoặc `instanceof` false.
- Những vi phạm **loading constraint** nhất định có thể làm quá trình linking thất bại với `LinkageError`.
- Không có một exception duy nhất bắt buộc cho mọi tình huống class-loader mismatch; phải xem đang cast, access, resolve hay override/interface method.

**Không tự sửa bằng cách vô hiệu hóa verifier hay bỏ qua kiểm tra kiểu.** Nếu class identity thực sự xung đột, phải thiết kế lại delegation, API boundary và dependency visibility.

### 12.1. Vì sao `LinkageError` khác `ClassNotFoundException`?

`ClassNotFoundException` thường phát sinh khi API nạp class theo tên (ví dụ `loadClass` hoặc `Class.forName`) không tìm được binary representation phù hợp. Các lỗi liên kết khác có thể xuất hiện khi class đã được tìm nhưng **không thể kiểm tra, resolve, định nghĩa hoặc liên kết hợp lệ** với những class đã có.

`NoClassDefFoundError` có thể xuất hiện khi runtime cần một class nhưng không thể xác định định nghĩa hoặc class initialization trước đó thất bại. Không nên gộp tất cả thành “JVM không tìm thấy JAR”.

## 13. Những vấn đề dễ mắc với custom class loaders

### 13.1. Định nghĩa cùng binary name hai lần trong cùng loader

Một loader được thiết kế đúng nên trả lại class đã định nghĩa cho cùng tên khi nạp lại. Nếu gọi `defineClass` trùng một binary name lần thứ hai trong cùng một loader, có thể gặp `LinkageError` liên quan duplicate class definition.

Trong ví dụ, `findLoadedClass(name)` ngăn lỗi này cho loader một khi gọi lại `loadClass(name)`.

### 13.2. Không đồng bộ khi nhiều thread nạp cùng tên

Hai thread cùng yêu cầu một class có thể đua nhau tới đoạn `defineClass` nếu loader không xử lý locking/caching đúng. Sử dụng API/khóa theo hợp đồng class loading là cần thiết. Ví dụ dùng `getClassLoadingLock(name)`; mọi custom loader thực tế còn cần tính toán rõ chiến lược nạp đồng thời, nhất là khi chọn parallel-capable loaders.

### 13.3. Bỏ qua parent khiến các API chuẩn bị nhân bản

Tự định nghĩa lại quá nhiều class có thể phá vỡ object compatibility. Parent delegation giúp chia sẻ các class cốt lõi và hợp đồng API theo thiết kế, nhưng vẫn cần phân biệt **class được yêu cầu** với **class được định nghĩa**.

### 13.4. Truyền `ClassLoader` mà không biết nó có delegate hay không

`Class.forName(name, false, loader)` và `loader.loadClass(name)` không có nghĩa class nhận được chắc chắn do loader truyền vào định nghĩa. Kiểm tra thêm `result.getClassLoader()` để biết defining loader.

### 13.5. Tên loader object đẹp không làm hai class tương đương

Hai loader cùng loại và cùng `toString()` vẫn có thể là hai loader khác nhau. Nếu cần kiểm tra chính xác, dùng identity của loader object và class object; đừng dựa vào friendly name trong log.

### 13.6. Dùng classpath hoặc JAR đúng nhưng vẫn cast lỗi

Một class file nằm đúng JAR trên disk không giải thích đủ runtime identity: **loader nào đã dùng bytecode để định nghĩa class** mới là vấn đề. Cùng JAR được mở bởi hai URLClassLoader độc lập có thể tạo hai class runtime cho cùng binary name nếu cả hai tự định nghĩa chúng.

### 13.7. Giữ class loader cũ khiến không unload được class

Class unloading phụ thuộc reachability và hành vi GC/runtime. Nếu host vô tình giữ references tới loader/plugin classes/objects hoặc những thành phần như thread/context class loader, static caches, listener, ThreadLocal, v.v., class loader cũ có thể còn reachable và class metadata không được thu hồi như mong đợi.

Không giả định “hủy JAR file hoặc đóng URLClassLoader là mọi class lập tức được unload”. Vòng đời plugin phải giải phóng các reference liên quan; việc GC có/không xảy ra lúc nào là chuyện khác.

## 14. Thread context class loader không phải defining loader

Java có API `Thread.currentThread().getContextClassLoader()`, thường được các framework hoặc service-loading mechanism sử dụng để tìm resource/class qua một loader phù hợp ngữ cảnh.

Ví dụ:

```java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
```

Đây là **đoạn mã minh họa trong một phương thức**. Context loader không phải thuộc tính định danh trực tiếp của mọi class đang chạy; nó có thể thay đổi theo thread hoặc framework. Không nên cho rằng `contextLoader == SomeType.class.getClassLoader()` luôn đúng.

Ba câu hỏi cần tách khi debug:

1. **Ai bắt đầu yêu cầu nạp?** Có thể là class/module code, framework hoặc context loader.
2. **Loader nào cuối cùng định nghĩa class?** Kiểm tra `Class.getClassLoader()`.
3. **Class nào đang được dùng ở boundary?** So sánh exact `Class` objects, method parameter types và interface identity.

Một thread context loader chỉ là **đầu mối tìm kiếm/ủy quyền theo ngữ cảnh**; không thay đổi defining loader của một class đã tồn tại.

## 15. Module system và class-loader identity

Từ Java 9, **JPMS** bổ sung module graph, readability, exports/opens và module layers. Nó ảnh hưởng việc tìm, đóng gói và truy cập class. Nhưng không thay đổi kết luận chủ đạo: **class/interface runtime vẫn được xác định bằng binary name và defining loader**, đồng thời còn phải thỏa các quy tắc module liên quan.

Không đồng nhất:

- **Module name** như `com.example.app`.
- **Package name** như `com.example.service`.
- **Binary class name** như `com.example.service.Worker`.
- **Defining class loader object** của một runtime class.

Ví dụ hai module layers có thể dẫn tới cấu trúc class loaders khác nhau. Cùng một nội dung artifact không chứng minh hai runtime classes được chia sẻ, nếu cách bố trí class loader tạo ra những định nghĩa độc lập.

Để debug JPMS nên xem cả `Class.getModule()` và `Class.getClassLoader()`; hai API trả thông tin khác nhau. Đừng dùng module name làm thay thế loader identity.

## 16. Công cụ kiểm tra và cách đọc log

### 16.1. In tên và defining loader có kiểm soát

```java
static void describe(Class<?> type) {
    System.out.println("name: " + type.getName());
    System.out.println("loader: " + type.getClassLoader());
    System.out.println("module: " + type.getModule().getName());
}
```

Đây là **mã minh họa phương thức**, không phải chương trình độc lập. `getClassLoader() == null` thường tương ứng bootstrap; `getModule().getName()` có thể trả null với unnamed module.

Tên loader chỉ hỗ trợ đọc log; muốn biết hai loader có phải cùng đối tượng, so sánh `==`. Trong những môi trường có nhiều bản triển khai `toString()` khác nhau, không nên diễn giải output của loader như một ID ổn định toàn hệ thống.

### 16.2. Truy nguyên lý do cast sai

Khi thấy `ClassCastException` lạ:

1. Lấy **Class object** của đối tượng thật bằng `value.getClass()` (nếu value khác null).
2. Lấy **Class object** của kiểu API đích bằng `Target.class` hoặc reflection thích hợp.
3. So sánh **tên nhị phân** của hai `Class`.
4. So sánh **defining loaders** qua `getClassLoader()`, rồi so sánh chính các `Class` objects.
5. Kiểm tra loader delegation policy và dependency JAR/version mapping.
6. Nếu boundary đi qua interface, kiểm tra interface `Class` mà host và plugin đang sử dụng có cùng identity không.

`value.getClass().getName().equals(Target.class.getName())` cho kết quả true **không kết thúc quá trình điều tra**; cần xem loader.

### 16.3. Ghi log class loading khi cần

Trong nhiều JDK hiện đại có Unified Logging:

```bash
java -Xlog:class+load=info ClassIdentityDemo
```

Cú pháp và chi tiết output log có thể thay đổi theo JVM/phiên bản. Lệnh minh họa phù hợp với HotSpot/JDK thường dùng; không coi mọi tùy chọn `-Xlog` là một phần của mọi Java implementation.

Log có thể cho biết tên class và nguồn bytecode, nhưng để xác định identity trong mã, **`Class` object và defining loader** là bằng chứng trực tiếp hơn. Nếu class loading log quá nhiều, dùng mức/tag phù hợp với JVM đích.

### 16.4. Xem class file không cho biết toàn bộ runtime loader identity

`javap -v` cho biết binary name, constant pool, descriptors và nội dung class file, nhưng file trên đĩa **không tự có một defining loader runtime duy nhất**. Tệp bytecode có thể được đọc bởi nhiều loader và tạo nhiều class runtime.

Đây là lý do không thể chỉ dùng `javap` hoặc hash SHA-256 của `.class` để kết luận “đó là cùng `Class` trong JVM”. Cần kết hợp dữ liệu class file với thông tin class loading runtime.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Binary name đủ để định danh class.” | Phải xét **(binary name, defining loader)**. |
| “Hai tệp `.class` giống byte-for-byte thì là cùng kiểu.” | Hai loaders định nghĩa riêng vẫn có thể tạo hai kiểu runtime khác nhau. |
| “Loader nào gọi `loadClass` là defining loader.” | Nó có thể **delegate** và chỉ là initiating loader. |
| “Hai loader cùng class `URLClassLoader` nên cùng identity.” | Mỗi loader **instance** là một đối tượng riêng. |
| “`Class.getName()` giống nhau nên có thể cast.” | Cast phải kiểm tra runtime class/assignability, không chỉ chuỗi tên. |
| “Package cùng tên là cùng runtime package.” | Còn phụ thuộc **defining loader**. |
| “Array class có tệp `.class` riêng do loader định nghĩa.” | Array class được JVM tạo; defining loader theo component type. |
| “`int[]` do custom loader định nghĩa nếu code plugin tạo nó.” | Primitive array type gắn với bootstrap, không do loader plugin tự định nghĩa. |
| “Class loading cũng là chạy `static`.” | Loading/linking và initialization là các giai đoạn khác nhau. |
| “Context class loader luôn là defining loader.” | Chúng phục vụ các mục đích khác nhau. |
| “Đóng loader/JAR sẽ unload class ngay.” | Class unloading tùy reachability/GC, không có thời điểm tức thì bảo đảm. |
| “Bỏ parent-first hoàn toàn sẽ làm plugin độc lập an toàn hơn.” | Có thể nhân bản API, gây ClassCastException/LinkageError và không tạo sandbox bảo mật. |
| “JPMS thay thế hoàn toàn class loader.” | Modules và loaders cùng tham gia tổ chức/kiểm tra runtime; không thay định danh cặp theo JVMS. |

## 18. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Hai loader riêng `A` và `B` cùng đọc một tệp `Task.class` có binary name `app.Task`. Nếu cả hai trực tiếp gọi `defineClass` thành công, hai class có cùng identity không?

**Đáp án:** Không. Cặp `(app.Task, A)` và `(app.Task, B)` khác nhau, dù bytes giống hệt.

**Câu 2.** Loader plugin `P` delegate nạp `java.lang.String` cho bootstrap. Defining loader của String là ai?

**Đáp án:** Bootstrap loader theo JDK tiêu chuẩn. `P` có thể là initiating loader, không phải defining loader của String.

**Câu 3.** Vì sao `Class.getName()` không đủ chứng minh object cast được?

**Đáp án:** Nó không chứa defining loader identity. Phải xét runtime class và quan hệ assignability.

**Câu 4.** Binary name của member class `Outer.Inner` có thể là gì?

**Đáp án:** Thông thường `Outer$Inner` (kèm package tương ứng). Dấu chấm source giữa Outer và Inner không phải dấu chấm của binary name.

**Câu 5.** Hai custom loader cùng class và cùng parent có thể định nghĩa hai bản `Plugin` khác nhau không?

**Đáp án:** Có, nếu mỗi **loader instance** tự định nghĩa cùng binary name. Cùng parent không buộc phải chia sẻ mọi class.

**Câu 6.** Cùng tên package, hai class do hai defining loaders khác nhau tạo, có mặc nhiên cùng runtime package?

**Đáp án:** Không. Runtime package liên quan **package name và defining loader**.

**Câu 7.** Hai array types `Plugin[]` có thể khác identity khi component classes cùng binary name không?

**Đáp án:** Có. Nếu component classes có defining loaders khác nhau, array classes tương ứng cũng khác identity.

**Câu 8.** `int[].class.getClassLoader()` là custom loader của class đã viết `new int[3]`?

**Đáp án:** Không. Primitive array class do JVM tạo và gắn với bootstrap loader.

**Câu 9.** Nếu host và plugin cần dùng chung `api.Task`, thường nên nạp API như thế nào?

**Đáp án:** Để một loader chung (thường là parent/host loader) định nghĩa `api.Task`, plugin loaders delegate kiểu API đó. Implementation vẫn có thể được định nghĩa riêng.

**Câu 10.** `Class.forName(name, false, loader)` có làm loader đã truyền thành defining loader không?

**Đáp án:** Không bắt buộc. Loader có thể delegate; flag `false` nói về việc không yêu cầu initialization, không thay defining loader.

**Câu 11.** `ClassCastException` và `LinkageError` trong hệ nhiều loader có cùng nguyên nhân duy nhất không?

**Đáp án:** Không. Cast mismatch và loading/linking constraint failure là những vấn đề khác nhau, dù đôi khi cùng liên quan các kiểu trùng binary name nhưng khác loader.

**Câu 12.** Hai plugin dùng cùng class file nhưng đều được định nghĩa độc lập. Một plugin có thể gọi trực tiếp package-private member của plugin kia chỉ vì chuỗi package giống không?

**Đáp án:** Không thể mặc định như vậy. Runtime package có cả defining loader, và JVM còn kiểm tra quyền truy cập/module khi thích hợp.

## 19. Tổng kết

```text
                     Binary name
                         +
                Defining class loader
                         |
                         v
                Runtime class identity
                         |
              +----------+----------+
              |                     |
         Class checks           Linkage checks
      cast / instanceof      method / field / API
              |                     |
              +----------+----------+
                         |
              Chính sách class loading
             (delegation, isolation, APIs)
```

Điểm cần ghi nhớ:

1. **Không định danh Java runtime class chỉ bằng tên.** Cặp **(binary name, defining loader)** mới quyết định class/interface identity.
2. **Initiating loader khác defining loader.** Delegation có thể khiến nhiều loaders cùng sử dụng một định nghĩa runtime.
3. **Cùng bytecode không đồng nghĩa cùng kiểu.** Hai loaders độc lập có thể tạo hai class `Class` khác nhau và khiến cast thất bại.
4. **Array classes có quy tắc đặc biệt:** JVM trực tiếp tạo array class, còn defining loader của array class được xác định từ component type.
5. **Runtime package và liên kết cũng phụ thuộc loader.** Thiết kế plugin cần chia sẻ API contract phù hợp và cô lập implementation có kiểm soát.
6. **Debug phải nhìn cả name, Class object, loader và module khi cần.** Đây là cơ sở để giải quyết những lỗi type mismatch vốn nhìn bề ngoài rất khó hiểu.

### Tài liệu đặc tả và API chính thức

- [JVMS §5.3 — Creation and Loading (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): cặp binary name + defining loader, initiating/defining loaders, array classes.
- [JVMS §5.3.3 — Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.3): quy tắc array class/defining loader theo component type.
- [JVMS §5.3.4 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.4): những ràng buộc an toàn kiểu trong liên kết.
- [JVMS §4.2.1 — Binary Class and Interface Names](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.2.1): dạng tên nhị phân của class/interface.
- [JLS §13.1 — The Form of a Binary (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.1): binary names và liên kết nhị phân.
- [ClassLoader API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `defineClass`, delegation.
- [Class API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isInstance`, `cast`.
