# Định danh kiểu annotation khi dùng nhiều class loader trong Java

## 1. Bài toán: cùng tên annotation nhưng không tìm thấy giá trị

Một ứng dụng Java có thể tải mã từ nhiều nguồn: chương trình chính, plugin, module mở rộng, công cụ phát triển hoặc môi trường chạy ứng dụng. Khi đó, mã có thể được nạp bởi **những class loader khác nhau**.

Giả sử một class được chú thích:

```java
@Feature("payment")
public class PaymentPlugin {}
```

Annotation `Feature` đã khai báo `@Retention(RetentionPolicy.RUNTIME)`, nhưng đoạn mã ở chương trình chính vẫn có thể nhận kết quả `null`:

```java
Feature feature = pluginClass.getAnnotation(Feature.class);
```

Một nguyên nhân quan trọng là **`Feature.class` bên chương trình chính không có cùng định danh kiểu với `Feature` đã được dùng trong class plugin**. Chúng có thể có cùng tên nhị phân (*binary name*), cùng mã bytecode và cùng các element, nhưng được định nghĩa bởi các class loader khác nhau.

Trong Java, tên đầy đủ **chưa đủ** để xác định duy nhất một kiểu tại runtime. Bài học này tập trung vào ý nghĩa của định danh kiểu annotation, tác động đến giá trị annotation được đọc qua reflection, cách kiểm tra chẩn đoán và cách thiết kế ranh giới class loader.

## 2. Định danh của một kiểu Java tại runtime

Theo mô hình JVM, định danh của một class hoặc interface tại runtime được xác định bởi **tên nhị phân** và **class loader định nghĩa kiểu đó** (*defining class loader*).

Có thể diễn đạt:

```text
Runtime type identity = (binary name, defining class loader)
```

Với một annotation type cũng vậy, vì annotation type là một dạng interface chuyên biệt.

Ví dụ hai class loader độc lập:

```text
Loader A                              Loader B
   │                                     │
   ├── demo.Feature  [Feature@A]         ├── demo.Feature  [Feature@B]
   └── demo.Plugin   [Plugin@A]          └── demo.Plugin   [Plugin@B]

Feature@A.getName() == Feature@B.getName()   → true
Feature@A == Feature@B                       → false
```

Ở đây `Feature@A` và `Feature@B` chỉ là ký hiệu minh họa cho hai đối tượng `Class<?>` khác nhau, không phải cú pháp tên kiểu Java.

Trong một JVM:

- `Class.getName()` có thể trả cùng chuỗi, chẳng hạn `demo.Feature`, cho hai kiểu riêng biệt.
- So sánh đối tượng `Class<?>` bằng `==` kiểm tra **đúng định danh kiểu**, nên kết quả là `false` nếu hai defining loader thực sự khác nhau.
- `Class.getClassLoader()` cho biết loader định nghĩa lớp tương ứng; với một số lớp nền tảng được bootstrap loader định nghĩa, API này có thể trả `null`.
- Hai kiểu riêng biệt không tự tương thích khi ép kiểu, gọi `isInstance` hoặc dùng làm tham số `getAnnotation`, dù bytecode và các tên phần tử giống hệt.

### Defining loader khác initiating loader

Một class loader có thể **ủy quyền** việc nạp class cho loader cha. Loader nhận yêu cầu ban đầu có thể không phải loader **định nghĩa** class được trả về.

Chẳng hạn, Loader Plugin gọi `loadClass("api.Feature")`, nhưng nếu parent delegation chuyển yêu cầu lên Loader App và Loader App định nghĩa `api.Feature`, thì cả hai phía có thể nhận cùng một đối tượng `Class<?>`. Khi đó **không xảy ra hai định danh kiểu** cho `api.Feature`.

Do vậy, đừng kết luận “plugin có class loader riêng” đồng nghĩa “mọi class của plugin đều được định nghĩa lại”. Điều quyết định là **loader nào thực sự định nghĩa annotation type**.

## 3. Annotation type cũng có danh tính độc lập với tên

Một định nghĩa annotation bình thường:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Feature {
    String value();
}
```

Nếu cùng file `demo/Feature.class` được hai loader độc lập định nghĩa, ta có hai annotation interface tại runtime. Mỗi kiểu có element `value()` trả `String`, cùng tên `demo.Feature`, cùng retention `RUNTIME`, nhưng JVM vẫn coi là **hai kiểu khác nhau**.

Với một lần sử dụng annotation trên class `demo.Plugin` được nạp bởi Loader A, metadata được giải quyết thành kiểu `Feature@A` theo môi trường tải và phân giải của lớp đó. Khi API của chương trình chính truyền `Feature@B.class` vào `getAnnotation`, API phải tìm annotation **đúng kiểu `Feature@B`** chứ không tìm chỉ theo chuỗi tên.

Đây là nguyên tắc quan trọng:

> Runtime reflection tìm annotation bằng **đối tượng `Class` của annotation type**, không phải chỉ bằng tên chuỗi.

Sự trùng khớp về `value()`, retention hay đường dẫn của file `.class` không biến hai kiểu từ các loader khác nhau thành một kiểu duy nhất.

## 4. Điều kiện đọc annotation bằng reflection

Ngay cả khi đã dùng đúng class loader, vẫn cần những điều kiện thông thường:

1. **Annotation type có `@Retention(RetentionPolicy.RUNTIME)`.** Nếu mặc định `CLASS` hoặc đặt `SOURCE` thì `Class.getAnnotation(...)` không thấy metadata qua reflection chuẩn.
2. **Đối tượng được truy vấn là thành phần có annotation.** `Class<?>` đọc annotation cấp class; annotation trên method cần truy vấn đúng `Method`, annotation trên package cần truy vấn `Package`.
3. **Kiểu annotation truyền vào phải trùng định danh runtime.** `pluginClass.getAnnotation(annotationClass)` dùng chính `Class<A>` được truyền vào.
4. **Class và annotation type phải tải/được phân giải thành công.** Các vấn đề classpath, dependency bị thiếu hoặc class loader không đọc được metadata có thể gây lỗi khi phản chiếu.
5. **Khi annotation lặp, chọn API phù hợp.** `getAnnotationsByType(...)` có thể đọc các giá trị trong container repeatable; `getAnnotation(...)` không tự bung container chứa nhiều annotation.

Một kết quả `null` từ `getAnnotation` không cho biết nguyên nhân duy nhất. Nó có thể do không gắn annotation, retention không phù hợp, truy vấn sai vị trí, chỉ có repeatable container, hoặc do kiểu annotation từ class loader khác.

Cách điều tra đáng tin là kiểm tra **annotation được khai báo trên element nào**, **kiểu runtime thực tế của annotation**, và **class loader định nghĩa từng kiểu**.

## 5. Chương trình Java 17+ đầy đủ: hai loader nạp cùng annotation type

Ví dụ dưới đây chứng minh sự khác nhau bằng hai `URLClassLoader` độc lập nạp **cùng thư mục class file**. Chúng có parent `null` để không ủy quyền kiểu `demo.Feature` cho application class loader. Các lớp Java nền tảng vẫn được JVM cung cấp thông qua bootstrap loading.

Tạo cấu trúc:

```text
src/
├── LoaderIdentityDemo.java
└── demo/
    ├── Feature.java
    └── Plugin.java
```

### File `src/demo/Feature.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Feature {
    String value();
}
```

### File `src/demo/Plugin.java`

```java
package demo;

@Feature("isolated")
public class Plugin {
}
```

### File `src/LoaderIdentityDemo.java`

```java
import java.lang.annotation.Annotation;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[0]).toAbsolutePath();
        URL location = output.toUri().toURL();
        URL[] paths = {location};

        try (URLClassLoader first = new URLClassLoader(paths, null);
             URLClassLoader second = new URLClassLoader(paths, null)) {

            Class<? extends Annotation> featureA =
                    Class.forName("demo.Feature", true, first)
                         .asSubclass(Annotation.class);
            Class<? extends Annotation> featureB =
                    Class.forName("demo.Feature", true, second)
                         .asSubclass(Annotation.class);

            Class<?> pluginA = Class.forName("demo.Plugin", true, first);
            Class<?> pluginB = Class.forName("demo.Plugin", true, second);

            Annotation foundWithA = pluginA.getAnnotation(featureA);
            Annotation foundWithB = pluginA.getAnnotation(featureB);

            System.out.println("same name="
                    + featureA.getName().equals(featureB.getName()));
            System.out.println("same Class="
                    + (featureA == featureB));
            System.out.println("same Plugin Class="
                    + (pluginA == pluginB));
            System.out.println("same defining loader="
                    + (featureA.getClassLoader() == featureB.getClassLoader()));
            System.out.println("found with own type="
                    + (foundWithA != null));
            System.out.println("found with foreign type="
                    + (foundWithB != null));
            System.out.println("annotationType matches own="
                    + (foundWithA.annotationType() == featureA));
            System.out.println("foreign type accepts annotation="
                    + featureB.isInstance(foundWithA));
            System.out.println("annotation value="
                    + featureA.getMethod("value").invoke(foundWithA));
        }
    }
}
```

Từ thư mục chứa `src`, dùng JDK 17 trở lên:

```bash
javac -d out src/demo/Feature.java src/demo/Plugin.java src/LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo out
```

**Stdout dự kiến, theo thứ tự:**

```text
same name=true
same Class=false
same Plugin Class=false
same defining loader=false
found with own type=true
found with foreign type=false
annotationType matches own=true
foreign type accepts annotation=false
annotation value=isolated
```

### Vì sao chương trình có kết quả ấy?

- Cả Loader A và Loader B đọc cùng bytecode `demo.Feature`. Chuỗi `getName()` bằng nhau.
- Vì mỗi `URLClassLoader` được tạo độc lập và đều tự định nghĩa `demo.Feature`, `featureA == featureB` là `false`.
- `demo.Plugin` cũng được định nghĩa riêng trong từng loader, nên `pluginA != pluginB`.
- `@Feature("isolated")` trong `Plugin@A` được phân giải thành annotation type `Feature@A`.
- `pluginA.getAnnotation(featureA)` tìm thấy annotation. `pluginA.getAnnotation(featureB)` không tìm thấy vì truyền kiểu từ Loader B.
- `foundWithA.annotationType()` trả đúng đối tượng kiểu `featureA`.
- `featureB.isInstance(foundWithA)` là `false` vì instance annotation ấy không hiện thực hóa interface `Feature@B`.
- Reflection gọi `value()` trên **chính `featureA`** trả chuỗi `"isolated"` mà không cần compile-time import `demo.Feature` vào chương trình điều phối.

Ví dụ đặt `demo.Feature` và `demo.Plugin` trong cùng output directory cho dễ thử nghiệm. Trong thực tế, hai loader có thể đọc từ các JAR khác nhau hoặc hai bản sao của một dependency; bản chất định danh kiểu vẫn như nhau.

**Giới hạn có chủ ý:** Chương trình điều phối không ép kiểu kết quả thành `demo.Feature` tại compile time. Nó dùng interface chuẩn `Annotation` và reflection để làm việc với kiểu annotation mà loader tương ứng trả về.

## 6. `Annotation.annotationType()`: phân biệt kiểu thực với tên hiển thị

Khi đã đọc được một instance annotation:

```java
Annotation annotation = someAnnotation;
Class<? extends Annotation> actualType = annotation.annotationType();
```

`annotationType()` trả **đối tượng `Class` đại diện đúng annotation interface** của instance đó. Đây là cơ sở đáng tin hơn việc chỉ cắt tên từ `toString()`.

Ví dụ cách chẩn đoán trong một helper:

```java
import java.lang.annotation.Annotation;

class AnnotationDiagnostic {
    static void printIdentity(Annotation annotation) {
        Class<? extends Annotation> type = annotation.annotationType();
        ClassLoader loader = type.getClassLoader();
        System.out.println("annotation name: " + type.getName());
        System.out.println("defining loader: " + loader);
    }
}
```

Helper này minh họa và sẽ biên dịch khi đặt trong file `AnnotationDiagnostic.java`; output của `ClassLoader.toString()` phụ thuộc môi trường, vì vậy **không có một chuỗi stdout cố định** cần thuộc.

Muốn so đúng kiểu:

```java
boolean sameRuntimeType =
        left.annotationType() == right.annotationType();
```

Nếu chỉ so:

```java
boolean sameBinaryName =
        left.annotationType().getName()
                .equals(right.annotationType().getName());
```

thì bạn mới biết **tên bằng nhau**, chưa chứng minh hai annotation có cùng định danh kiểu.

### Không dùng `toString()` hoặc `hashCode()` để phân biệt class loader

`Annotation.toString()` chủ yếu phục vụ biểu diễn để đọc; kết quả có thể giống nhau dù hai kiểu là khác nhau. `hashCode()` của annotation được quy định dựa trên tên và giá trị element; nó không phải khóa định danh loader.

`Annotation.equals(...)` cũng có hợp đồng so sánh kiểu annotation và các element. Hai annotation instance khác định danh kiểu sẽ không trở thành một annotation cùng kiểu chỉ vì chúng có cùng tên và cùng các giá trị. Nếu cần nhận diện ranh giới loader, so sánh `annotationType()` hoặc dùng `Class.isInstance(...)` phù hợp.

## 7. Vì sao ép kiểu annotation có thể gây `ClassCastException`?

Giả sử ứng dụng biên dịch với một annotation type `api.Flag` do loader của ứng dụng định nghĩa, nhưng một plugin lại chứa bản copy `api.Flag` do loader plugin định nghĩa.

Phía host có thể viết:

```java
// Ví dụ minh họa: annotation được plugin cung cấp.
Annotation candidate = obtainPluginAnnotation();

// Có thể gây ClassCastException nếu candidate thuộc api.Flag của loader khác.
Flag flag = (Flag) candidate;
```

Đây chỉ là mảnh mã minh họa, giả định `Flag` và `obtainPluginAnnotation()` đã tồn tại. Lỗi có thể biểu hiện như hai kiểu mang cùng tên package và class nhưng thuộc hai loader khác nhau.

Một cách kiểm tra an toàn hơn:

```java
if (Flag.class.isInstance(candidate)) {
    Flag flag = Flag.class.cast(candidate);
    System.out.println(flag.value());
} else {
    System.out.println("Incompatible annotation runtime type");
}
```

`isInstance` kiểm tra **khả năng gán theo định danh runtime thực**, không suy luận từ tên. Nếu kiểu không khớp, cần sửa cấu trúc class loader hoặc cách chia sẻ API; không nên ép kiểu cưỡng bức hay cho rằng hai annotation type được hợp nhất.

Cũng có thể xảy ra `ClassCastException` khi các interface/class trong **element value** hoặc hợp đồng plugin bị định nghĩa trùng; class loader ảnh hưởng đến nhiều kiểu, không riêng annotation.

## 8. Quan hệ với `Class<?>` trong giá trị annotation

Annotation có thể khai báo element kiểu `Class<?>`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface HandlerType {
    Class<?> value();
}
```

Sử dụng:

```java
@HandlerType(MyHandler.class)
class HandlerOwner {}
```

Giá trị của `HandlerType.value()` khi được đọc là một đối tượng `Class<?>` đại diện kiểu handler được tham chiếu trong metadata. Trong môi trường nhiều loader, **định danh của `MyHandler` cũng phụ thuộc defining loader**, không chỉ tên.

Điều này có hai hệ quả:

- `value().getName()` có thể giống tên một class của host nhưng `value() == HostHandler.class` vẫn `false`.
- Nếu hệ thống dùng class literal này để chọn/khởi tạo handler, cần kiểm tra nó có thực sự implement interface được chia sẻ qua đúng loader không, ví dụ `Service.class.isAssignableFrom(handlerClass)`.

Đừng coi một chuỗi tên như `"demo.MyHandler"` là bằng chứng các đối tượng `Class<?>` giống nhau. Phản chiếu thực sự chỉ đáng tin khi bạn xác định được loader sở hữu type và quan hệ kế thừa tương ứng.

Nếu class được tham chiếu trong giá trị annotation không thể được tải hoặc phân giải khi đọc element, quá trình truy cập có thể phát sinh lỗi như `TypeNotPresentException` hoặc các lỗi liên quan class loading. Nên xử lý lỗi theo ngữ cảnh plugin, dependency và classpath thực tế.

## 9. Annotation lặp và container khi có nhiều loader

Một repeatable annotation được định nghĩa bởi cặp kiểu:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
```

`@Repeatable(Tags.class)` chỉ tới **một annotation type container cụ thể**, còn `Tags.value()` trả mảng của **đúng annotation type `Tag`**. Nếu một plugin định nghĩa cả `Tag` và `Tags` bằng loader riêng, thì host định nghĩa cặp kiểu cùng tên bằng loader khác sẽ không tự có cùng danh tính.

Vì vậy, code kiểu:

```java
Tag[] tags = pluginClass.getAnnotationsByType(Tag.class);
```

có thể trả mảng rỗng nếu `Tag.class` ở host không phải kiểu `Tag` mà `pluginClass` thực sự sử dụng. `getAnnotationsByType` có khả năng mở container **cùng hệ kiểu**, nhưng không “gộp” các annotation type chỉ vì `Tag` và `Tags` của hai loader có cùng tên.

Khi hỗ trợ repeatable annotation qua ranh giới plugin, tốt nhất là chia sẻ **cả repeatable annotation và container type** trong một API chung để mọi thành phần tham chiếu đúng những đối tượng `Class` ấy.

### Đọc qua kiểu runtime đúng

Trong một chương trình khám phá plugin, có thể tìm kiểu annotation đã được plugin nạp:

```java
Class<?> unknown = Class.forName("demo.Tag", false, pluginLoader);
Class<? extends Annotation> actualTag =
        unknown.asSubclass(Annotation.class);

Annotation[] tags = pluginClass.getAnnotationsByType(actualTag);
```

Mã là mảnh minh họa cần `import java.lang.annotation.Annotation;` và biến `pluginLoader`/`pluginClass` đã có. Kết quả là mảng annotation mà runtime xem là đúng kiểu `actualTag`. Cách này hữu ích cho công cụ tổng quát, nhưng nếu host cần gọi element bằng interface Java có kiểu tĩnh, nên chia sẻ định nghĩa annotation giữa host và plugin thay vì chỉ làm việc với đối tượng `Annotation` chung.

## 10. Thiết kế class loader để host và plugin dùng chung annotation API

Đa số plugin systems muốn host có thể viết trực tiếp:

```java
Feature feature = pluginClass.getAnnotation(Feature.class);
```

Khi đó host và plugin **phải tham chiếu cùng định danh runtime của `Feature`**. Kiến trúc phổ biến:

```text
Bootstrap / Platform
        │
Application (shared API)
        ├── api.Feature
        ├── api.PluginService
        │
        ├── Plugin Loader A
        │      └── plugin.a.SomePlugin
        │
        └── Plugin Loader B
               └── plugin.b.OtherPlugin
```

Nguyên tắc:

1. Đặt `api.Feature` và các interface hợp đồng plugin trong một **artifact API chung**, do class loader cha hoặc một loader chung định nghĩa.
2. Đảm bảo loader plugin **ủy quyền các package API chung** về loader ấy, thay vì tự định nghĩa bản sao `api.Feature`.
3. Không đóng gói lại API thành một lớp riêng có cùng tên trong từng plugin nếu class loader plugin có thể định nghĩa lại nó; đặc biệt chú ý thiết lập *child-first*.
4. Kiểm tra tại runtime bằng `hostFeatureClass == pluginResolvedFeatureClass` và `getClassLoader()`, không chỉ dựa trên biểu đồ dependency lúc build.
5. Đóng gói các dependency nội bộ của plugin theo chính sách phù hợp; chỉ những kiểu cần được trao đổi qua ranh giới host–plugin mới bắt buộc có danh tính chung.

Một *plugin API* dùng chung có thể giúp host gọi trực tiếp các element, gắn cấu hình, kiểm tra `Service.class.isAssignableFrom(pluginClass)` và chuyển đối tượng qua ranh giới class loader một cách an toàn.

Trong thực tế, nếu dùng parent-first delegation mặc định, loader con thường nhận bản API từ cha khi cha có khả năng nạp nó. Với child-first loader hoặc shaded JAR, cần cấu hình ngoại lệ cho các package API. **Không nên giả định mặc định delegation áp dụng cho mọi custom loader**.

## 11. Cách chẩn đoán khi `getAnnotation` trả `null`

Khi một class plugin có vẻ được gắn annotation nhưng host không đọc được, hãy kiểm tra có thứ tự.

### Bước 1 — Kiểm tra retention và vị trí

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface PluginMarker {}
```

Cần annotation type có `RUNTIME` và annotation được gắn trên **đúng đối tượng** truy vấn. Nếu annotation nằm trên method, hãy hỏi `Method.getAnnotation(...)`. Nếu repeatable, dùng `getAnnotationsByType(...)`.

### Bước 2 — Kiểm tra kiểu mà host đang truy vấn

```java
Class<? extends Annotation> requested = PluginMarker.class;
System.out.println(requested.getName());
System.out.println(requested.getClassLoader());
```

Mảnh minh họa yêu cầu import `java.lang.annotation.Annotation`. Output về loader phụ thuộc runtime.

### Bước 3 — Liệt kê các annotation có trên class plugin

```java
for (Annotation a : pluginClass.getDeclaredAnnotations()) {
    Class<? extends Annotation> actual = a.annotationType();
    System.out.println(actual.getName());
    System.out.println(actual.getClassLoader());
    System.out.println(actual == requested);
}
```

Đây là mã minh họa giả định `pluginClass`, `requested` và import cần thiết đã có. Nếu tìm thấy một annotation có tên bằng `requested.getName()` nhưng `actual != requested`, đó là bằng chứng trực tiếp về **hai định danh kiểu khác nhau**.

Lưu ý: nếu annotation là repeatable và được chứa qua container, `getDeclaredAnnotations()` có thể liệt kê **container**. Khi đó cần kiểm tra container đúng loại rồi dùng `getDeclaredAnnotationsByType(actualRepeatableType)` hoặc quan sát nội dung container. Kết quả còn phụ thuộc retention và việc metadata có thể được phân giải tại runtime.

### Bước 4 — Kiểm tra loader thực sự định nghĩa kiểu

```java
Class<?> fromPlugin =
        Class.forName(requested.getName(), false,
                pluginClass.getClassLoader());

System.out.println(fromPlugin == requested);
```

Nếu kết quả là `false`, cùng tên đã được phân giải thành hai `Class<?>` khác nhau. Nếu kết quả là `true` thì loader plugin đã nhìn thấy đúng type được chia sẻ, và nên tiếp tục xem lại retention, target, vị trí và tình trạng biên dịch/đóng gói.

Đừng dùng `Class.forName(name)` không chỉ rõ loader như một phép thử đủ mạnh; lời gọi đó thường dùng loader của mã gọi và có thể không phải loader đang sở hữu class plugin.

### Bước 5 — Kiểm tra artifact và chính sách nạp

Kiểm tra thư viện API có bị sao chép vào nhiều JAR, bị shading, bị nhúng trong plugin, hoặc bị child-first loader nạp lại hay không. Nếu một class file bị thay đổi hoặc class loader dùng các rules riêng, không suy ra kết quả chỉ từ tên file.

Có thể kiểm tra bytecode bằng `javap -v` để xác nhận metadata ở cấp class khi cần. Tuy nhiên, class file chứa tên annotation **không nói đủ về defining loader sẽ dùng ở runtime**; cần quan sát cả môi trường đang chạy.

## 12. Những lỗi và hiểu nhầm phổ biến

| Hiện tượng | Sai lầm thường gặp | Cách xác minh và xử lý |
|---|---|---|
| `getAnnotation` trả `null` dù class có annotation | So trùng tên là đủ | So `Class<?>` của annotation thực tế với kiểu được yêu cầu; kiểm tra retention |
| `ClassCastException` khi ép annotation hoặc service | Hai class cùng tên nên coi cùng kiểu | Kiểm tra `isInstance`, `isAssignableFrom` và defining loader |
| `getName()` giống nhau nhưng `==` khác | “Cùng bytecode phải là cùng class” | Kiểm tra class loader thực sự định nghĩa kiểu |
| Plugin loader có parent là host nhưng vẫn trùng kiểu | Tưởng mọi custom loader đều parent-first | Xem `loadClass`/delegation policy và bản sao API trong JAR |
| Annotation lặp không được tìm bằng `getAnnotationsByType` | Container tự bắc cầu giữa loader | Chia sẻ cả repeatable type lẫn container type; kiểm tra đúng `Class` |
| `Feature.class` từ host đọc metadata của plugin thất bại | Chỉ sửa `@Retention` | Xác nhận đúng type identity; retention không sửa vấn đề loader |
| Một annotation có element `Class<?>` gây sự cố | Tên class value đủ để gọi được kiểu bên host | Xem định danh `Class<?>`, loader, phụ thuộc và khả năng phân giải |
| `toString()` trông giống nhau | Dùng chuỗi biểu diễn làm danh tính | Dùng `annotationType()` và `Class<?>` để kiểm tra |
| Công cụ reflection không lấy được annotation | Kết luận metadata chắc chắn không tồn tại | Phân biệt reflection runtime, bytecode scanner và artifact thực tế |

### Lỗi đặc biệt: lớp annotation có mặt nhưng element method không còn tương thích

Khi hai bên dùng các phiên bản khác nhau của một annotation API, lỗi không nhất thiết chỉ là `null`. Có thể gặp `IncompleteAnnotationException` khi annotation runtime thiếu giá trị bắt buộc theo phiên bản type hiện có, `AnnotationTypeMismatchException` khi kiểu giá trị element đã thay đổi, hoặc lỗi liên quan đến class/enum không còn tồn tại.

Những lỗi này liên quan **tiến hóa schema annotation và sự không tương thích binary**, có thể xảy ra ngay cả khi hai bên đã nhìn thấy cùng định danh kiểu tại runtime. Cần kiểm tra phiên bản dependency và biên dịch lại artifact phù hợp; không gán mọi lỗi reflection cho class loader.

## 13. Bài tập tự kiểm tra

Xét tình huống:

```text
PluginLoader1 ──> com.acme.audit.Audited (bản 1)
PluginLoader2 ──> com.acme.audit.Audited (bản 1)
HostLoader    ──> com.acme.audit.Audited (bản 1)
```

Giả sử ba loader **thực sự tự định nghĩa** annotation type theo từng bản sao, không chia sẻ qua parent. Class `com.acme.payments.Payment` do `PluginLoader1` định nghĩa được chú thích bằng `@Audited` có retention `RUNTIME`.

Hãy trả lời:

1. Ba đối tượng `Class<?>` của `com.acme.audit.Audited` có cùng `getName()` không?
2. `Audited` của PluginLoader1 có `==` `Audited` của HostLoader không?
3. Host dùng `Payment.class.getAnnotation(HostAuditedClass)` có mặc nhiên đọc được annotation đó không?
4. Nếu tìm đúng `Audited` từ PluginLoader1, có thể gọi `getAnnotation(...)` và lấy instance không?
5. `annotation.annotationType().getName()` bằng tên của `HostAuditedClass` có chứng minh hai kiểu giống nhau không?
6. Nếu PluginLoader1 được cấu hình ủy quyền package `com.acme.audit` cho HostLoader, còn code plugin dùng đúng API của host, hiện tượng có thể thay đổi như thế nào?
7. Hai annotation instance có cùng giá trị `value` nhưng thuộc interface do hai loader định nghĩa có được coi là cùng runtime annotation type không?
8. Một annotation lặp `@Label` và container `@Labels` chỉ được chia sẻ một trong hai kiểu có phải thiết kế chắc chắn cho reflection không?
9. Đổi `@Retention(CLASS)` sang `RUNTIME` có tự hợp nhất hai annotation interface do hai loader định nghĩa không?
10. Khi API ở host và plugin cùng tên nhưng khác định danh, hướng thiết kế nào thường phù hợp?

**Đáp án:**

1. **Có.** Cùng binary name.
2. **Không.** Defining loader khác nhau làm runtime type identity khác nhau.
3. **Không.** Query yêu cầu đúng annotation type từ HostLoader; metadata trên plugin dùng kiểu từ PluginLoader1.
4. **Có**, nếu metadata và quá trình nạp/phân giải hợp lệ. Truy vấn bằng đúng `Class<? extends Annotation>` của kiểu mà plugin dùng.
5. **Không.** Chuỗi tên chỉ chứng minh tên giống nhau; cần so đối tượng `Class<?>`.
6. **Có thể cùng định danh.** Nếu kiểu `Audited` do HostLoader định nghĩa và plugin thật sự được ủy quyền dùng bản đó, host và plugin sẽ cùng một `Class<?>`, giúp reflection và ép kiểu hợp lệ.
7. **Không.** Giá trị element giống nhau không thay đổi danh tính annotation type.
8. **Không.** Cặp repeatable/container nên được chia sẻ nhất quán, nếu muốn host đọc bằng kiểu Java đã biên dịch.
9. **Không.** Retention quyết định khả năng nhìn thấy metadata qua reflection, không hợp nhất kiểu giữa các loader.
10. **Đặt hợp đồng annotation/API dùng chung ở loader cha hoặc shared loader**, cấu hình delegation phù hợp và tránh để plugin tự định nghĩa lại các kiểu API cần trao đổi.

## 14. Checklist triển khai trong ứng dụng plugin

- Xác định annotation được dùng trên class, method, field, package hay type-use để chọn đúng đối tượng reflection.
- Khai báo `@Retention(RetentionPolicy.RUNTIME)` nếu consumer dùng Java reflection.
- Xác định binary name **và defining loader** của annotation type mà consumer truyền vào `getAnnotation`.
- Không lấy `Class.getName()` hoặc `Annotation.toString()` làm bằng chứng duy nhất của cùng định danh kiểu.
- So sánh `annotation.annotationType() == requestedType` hoặc dùng `Class.isInstance` khi cần kiểm tra chính xác.
- Phân biệt *initiating loader* và *defining loader*; kiểm tra parent delegation thực tế.
- Khi host dùng API annotation có kiểu tĩnh, chia sẻ định nghĩa annotation qua loader chung thay vì bundling bản riêng trong mỗi plugin.
- Với repeatable annotation, chia sẻ cả kiểu lặp và container, đồng thời chọn `getAnnotationsByType` khi cần đọc nhiều giá trị.
- Với element chứa `Class<?>`, kiểm tra khả năng tải và tương thích của kiểu được tham chiếu.
- Kiểm tra retention, bytecode, module/build artifact, classpath và dependency versions nếu reflection vẫn thất bại.
- Dùng một phép thử có hai loader thực sự độc lập để nhận diện vấn đề; đừng giả định một custom loader tự động tạo kiểu mới.
- Không cố ép kiểu đối tượng từ loader khác để che lỗi kiến trúc; xác định lại ranh giới hợp đồng dùng chung.

Khi làm việc với annotation trong hệ thống nhiều class loader, câu hỏi quan trọng nhất không chỉ là **“annotation có tên gì?”**, mà còn là **“đối tượng `Class` nào đại diện cho annotation đó, và loader nào định nghĩa nó?”**. Trả lời đúng hai câu hỏi này giúp phân biệt lỗi retention/lookup với lỗi định danh kiểu, từ đó thiết kế metadata giữa host và plugin ổn định hơn.