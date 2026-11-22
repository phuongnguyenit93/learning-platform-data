# Cùng tên lớp không bảo đảm cùng lớp khi có class loader khác nhau

## 1. Vấn đề: tên giống hệt nhưng JVM coi là hai kiểu khác nhau

Trong Java, hai đối tượng có thể in ra **cùng tên lớp đầy đủ** nhưng không thuộc **cùng một lớp lúc chạy**. Điều này xảy ra khi bytecode mang cùng tên nhị phân được **định nghĩa bởi hai class loader khác nhau**.

Ví dụ, một plugin và ứng dụng chủ cùng có tệp `com.example.model.Customer.class`. Nếu mỗi bên định nghĩa một bản sao riêng, hai đối tượng đều có thể báo:

```text
com.example.model.Customer
```

qua `getClass().getName()`. Tuy nhiên:

```java
left.getClass().getName().equals(right.getClass().getName()) // true
left.getClass() == right.getClass()                          // false
```

Đây là **fragment minh họa**; cần có hai đối tượng `left` và `right` tương ứng. Lý do là **tên dạng `String` không phải định danh duy nhất của lớp**.

Quy tắc cốt lõi dành cho kiểu tham chiếu thông thường trong JVM là: một lớp được nhận diện bằng **tên nhị phân (binary name)** kết hợp với **class loader định nghĩa (defining class loader)**. Có cùng tên nhưng có **defining loader khác nhau** thì là hai kiểu runtime khác nhau.

Điều này tác động trực tiếp đến `getClass()`, `instanceof`, ép kiểu (cast), gọi phương thức phản chiếu (reflection), overload nhận kiểu cụ thể, `equals()` và nhiều collection/API phụ thuộc kiểu đối tượng.

## 2. Phân biệt tên lớp, đối tượng `Class` và class loader

### Tên nhị phân và đối tượng `Class<?>`

`Class.getName()` trả một chuỗi mô tả tên nhị phân của class thông thường, ví dụ `java.lang.String` hoặc `com.example.Customer`. Với nested class, tên nhị phân có dấu `$`, chẳng hạn `Example$Value`.

`Class<?>` không chỉ là chuỗi tên. Nó là đại diện runtime cho một kiểu cụ thể đã được JVM nạp/định nghĩa. Hai class có cùng `getName()` vẫn có thể được biểu diễn bởi **hai đối tượng `Class` riêng biệt**.

```java
Class<?> typeA = objectA.getClass();
Class<?> typeB = objectB.getClass();

boolean sameText = typeA.getName().equals(typeB.getName());
boolean sameRuntimeType = typeA == typeB;
```

Các biến `objectA`/`objectB` là giả định của fragment này. Khi chỉ cần biết hai đối tượng có **chính xác cùng kiểu runtime**, so sánh `getClass()` bằng `==` (hoặc `Class.equals`) là đúng. Không dùng `getName().equals(...)` để thay cho kiểm tra kiểu.

### Class loader định nghĩa là gì?

Một `ClassLoader` có thể định vị bytecode và dùng `defineClass(...)` để tạo class trong JVM. **Loader nào thực sự định nghĩa class** là một phần bản sắc kiểu. Một loader khác có thể **yêu cầu nạp** class rồi nhận về chính class do loader cha định nghĩa; trong trường hợp đó, loader yêu cầu không phải defining loader.

```java
ClassLoader definingLoader = typeA.getClassLoader();
```

Với class do bootstrap class loader định nghĩa, `Class.getClassLoader()` thường trả `null`; `null` ở đây không có nghĩa class không được nạp.

JVM cũng có thể có nhiều loader cùng loại/class Java nhưng là **những instance khác nhau**. Hai instance ấy có thể định nghĩa hai bản sao runtime khác nhau của một tên class.

> Quy tắc cần nhớ: **tên đầy đủ + defining loader**, không phải chỉ tên file `.class`, tên package, đường dẫn JAR hoặc tên module.

## 3. Vì sao class loader khác nhau có thể nạp cùng tên?

Java thường dùng mô hình **ủy quyền cho loader cha (parent delegation)**: loader được yêu cầu trước tiên thử thông qua cha; nếu cha đã nạp/định nghĩa class thích hợp, các loader con có thể nhận về cùng một đối tượng `Class`. Vì thế **hai loader khác nhau không tự động đồng nghĩa hai class khác nhau**.

Các hệ thống plugin, máy chủ ứng dụng, container, IDE, công cụ reload hoặc môi trường cô lập có thể có chiến lược nạp tùy chỉnh. Một loader **child-first cho một tập tên được chọn** có thể định nghĩa bản sao riêng thay vì lấy bản đã tồn tại ở cha.

| Tình huống | Kết quả có thể xảy ra |
| --- | --- |
| Hai loader con đều ủy quyền cho cùng loader cha đã định nghĩa `SharedType` | Nhận **cùng** đối tượng `Class`, không có xung đột bản sắc kiểu |
| Hai loader khác nhau mỗi bên tự `defineClass` cùng tên `PluginType` | Có **hai** đối tượng `Class` khác nhau |
| Một loader đã định nghĩa một tên, lại cố định nghĩa cùng tên trong chính loader đó | Không được tạo hai class độc lập có cùng tên ở **cùng defining loader**; có thể phát sinh `LinkageError` |
| Hai bản JAR chứa tên class giống nhau | Chưa kết luận được gì nếu không biết class thực sự được loader nào định nghĩa |

Do đó không nên suy luận bản sắc kiểu chỉ từ việc nhìn thấy hai JAR hay hai `ClassLoader`. Phải quan sát **`Class<?>` thực tế của object**, cùng `getClassLoader()`, trong ngữ cảnh runtime.

## 4. Java 17: minh họa hai loader định nghĩa cùng một bytecode

Ví dụ này cố ý tạo **hai instance loader tùy chỉnh**, mỗi loader định nghĩa riêng nested class `ClassLoaderIdentityDemo$Value` từ cùng bytecode `.class`. Ngoài class `Value`, các tên khác vẫn được ủy quyền cho loader cha. Vì vậy hai `Value` là hai kiểu khác nhau, trong khi cả hai có thể triển khai **một interface dùng chung** `CodeView` do loader cha định nghĩa.

Tạo tệp duy nhất `ClassLoaderIdentityDemo.java` với nội dung sau:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

public class ClassLoaderIdentityDemo {

    public interface CodeView {
        String code();
    }

    public static class Value implements CodeView {
        private final String code;

        public Value(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public String code() {
            return code;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Value that = (Value) other;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static class IsolatedValueLoader extends ClassLoader {
        private final String targetName;
        private final byte[] targetBytes;

        IsolatedValueLoader(ClassLoader parent, String targetName,
                            byte[] targetBytes) {
            super(parent);
            this.targetName = targetName;
            this.targetBytes = targetBytes.clone();
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(targetName)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null) {
                    loaded = defineClass(
                            name, targetBytes, 0, targetBytes.length);
                }
                if (resolve) {
                    resolveClass(loaded);
                }
                return loaded;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String binaryName = Value.class.getName();
        String resourceName = "/" + binaryName.replace('.', '/')
                + ".class";

        byte[] bytes;
        try (InputStream stream =
                ClassLoaderIdentityDemo.class.getResourceAsStream(
                        resourceName)) {
            if (stream == null) {
                throw new IOException("Missing class resource: "
                        + resourceName);
            }
            bytes = stream.readAllBytes();
        }

        ClassLoader parent =
                ClassLoaderIdentityDemo.class.getClassLoader();
        ClassLoader loaderA =
                new IsolatedValueLoader(parent, binaryName, bytes);
        ClassLoader loaderB =
                new IsolatedValueLoader(parent, binaryName, bytes);

        Class<?> typeA = Class.forName(binaryName, true, loaderA);
        Class<?> typeB = Class.forName(binaryName, true, loaderB);
        Object a = typeA.getConstructor(String.class).newInstance("X");
        Object aAgain = typeA.getConstructor(String.class)
                .newInstance("X");
        Object b = typeB.getConstructor(String.class).newInstance("X");
        Value host = new Value("X");

        System.out.println("same binary name: "
                + typeA.getName().equals(typeB.getName()));
        System.out.println("same Class object: " + (typeA == typeB));
        System.out.println("same defining loader: "
                + (typeA.getClassLoader() == typeB.getClassLoader()));
        System.out.println("loader A owns type A: "
                + (typeA.getClassLoader() == loaderA));

        System.out.println("same-loader objects equal: "
                + a.equals(aAgain));
        System.out.println("cross-loader objects equal: "
                + a.equals(b));
        System.out.println("same hash allowed: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a instanceof host Value: "
                + (a instanceof Value));
        System.out.println("a implements shared CodeView: "
                + (a instanceof CodeView));
        System.out.println("shared interface call: "
                + ((CodeView) a).code());
        System.out.println("host equals a: " + host.equals(a));

        try {
            Value impossible = (Value) a;
            System.out.println(impossible.code());
        } catch (ClassCastException e) {
            System.out.println("host Value cast failed: true");
        }
    }
}
```

Biên dịch và chạy trong cùng thư mục bằng JDK 17 trở lên:

```bash
javac ClassLoaderIdentityDemo.java
java ClassLoaderIdentityDemo
```

Lưu ý: cần giữ các tệp `ClassLoaderIdentityDemo.class`, `ClassLoaderIdentityDemo$Value.class` và `ClassLoaderIdentityDemo$CodeView.class` mà `javac` tạo trong classpath lúc chạy. Chương trình đọc bytes của nested `Value` qua class resource, **không** phụ thuộc tên tuyệt đối của thư mục trên máy.

Đầu ra:

```text
same binary name: true
same Class object: false
same defining loader: false
loader A owns type A: true
same-loader objects equal: true
cross-loader objects equal: false
same hash allowed: true
a instanceof host Value: false
a implements shared CodeView: true
shared interface call: X
host equals a: false
host Value cast failed: true
```

### Điều gì diễn ra?

1. `Class.forName(binaryName, true, loaderA)` yêu cầu nạp tên thông qua `loaderA`. Vì loader tự xử lý **duy nhất** `Value`, nó gọi `defineClass` cho tên đó. `loaderB` thực hiện tương tự, tạo một định nghĩa khác.
2. Cả `typeA.getName()` và `typeB.getName()` có cùng chuỗi tên `ClassLoaderIdentityDemo$Value`, nên kết quả “same binary name” là `true`.
3. `typeA == typeB` là `false` và defining loader của chúng cũng khác nhau. Dù bytes y hệt, class trong JVM vẫn khác vì defining loader khác.
4. `a` và `aAgain` đều được tạo từ `typeA`. `Value.equals` thấy cùng class và cùng `code = "X"`, nên trả `true`.
5. `a.equals(b)` trả `false`: đối tượng `b` thuộc định nghĩa do `loaderB` tạo. Điều kiện `getClass() != other.getClass()` chặn việc cast sang kiểu `Value` của `a`.
6. `a.hashCode() == b.hashCode()` là `true` vì cả hai cùng hash chuỗi `"X"`; điều này **không chứng minh hai đối tượng bằng nhau**. Hợp đồng hash chỉ bắt buộc chiều `equals() == true => hashCode()` giống nhau.
7. `a instanceof Value` là `false` khi `Value` ở bên phải được biên dịch tham chiếu đến bản của **loader ứng dụng**. Đây là kiểm tra kiểu runtime, không phải so tên chuỗi.
8. `a instanceof CodeView` lại là `true` vì hai bản `Value` đều tham chiếu một `CodeView` được cha định nghĩa. Chuyển qua giao diện chia sẻ được và gọi `code()` trả `"X"`.
9. Ép `a` sang `Value` của ứng dụng ném `ClassCastException`. Chương trình in một dòng cố định trong `catch` thay vì in toàn bộ message ngoại lệ vì cách trình bày loader trong exception có thể phụ thuộc phiên bản JVM.

**Mục tiêu duy nhất của loader tùy chỉnh là minh họa bản sắc kiểu.** Đây không phải một class loader plugin hoàn chỉnh: production còn phải quản lý phạm vi tên, resource, bảo mật, giải phóng tham chiếu, caching và nhiều vấn đề tương thích khác. Không nên thay parent delegation bừa bãi cho mọi lớp.

## 5. Vì sao `getClass()` và `instanceof` phản ứng khác so với so tên?

### `getClass()` cho thấy đúng kiểu runtime

`getClass()` trả chính đối tượng `Class` đại diện cho kiểu thực tế của instance. Khi kiểm tra bằng:

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

một implementation `equals` **theo lớp chính xác** sẽ từ chối đối tượng do loader khác định nghĩa, ngay cả khi trường dữ liệu và tên lớp giống nhau.

Điều đó phù hợp với nhiều **value class không hỗ trợ quan hệ bằng nhau xuyên lớp**. Song `getClass()` không phải điều kiện bắt buộc cho mọi `equals`: những kiểu theo hợp đồng giao diện như `List`/`Set`/`Map` có thể định nghĩa bằng nhau xuyên lớp triển khai. Chọn chiến lược dựa trên **bản sắc logic**, không dùng một công thức chung cho toàn bộ Java.

### `instanceof` dùng quan hệ kiểu, không dùng tên

`obj instanceof SomeType` chỉ đúng khi kiểu runtime của `obj` là `SomeType` hoặc kiểu con/triển khai tương thích của **chính đối tượng Class tương ứng với `SomeType`**. Có cùng `getName()` không tạo quan hệ kế thừa.

```java
boolean exactType = obj.getClass() == SomeType.class;
boolean compatible = obj instanceof SomeType;
```

Fragment giả sử `obj` khác null và có kiểu `SomeType` nằm trong phạm vi biên dịch. Phép kiểm tra thứ nhất đòi **đúng lớp runtime**; thứ hai cho phép subclass/implementation hợp lệ. Cả hai không so khớp bằng tên text.

Trong ví dụ, `Value` của `loaderA` **không phải** subclass của `Value` của loader ứng dụng, nên `instanceof Value` thất bại. Nhưng cả hai có thể triển khai `CodeView` được nạp dùng chung, do đó `instanceof CodeView` thành công.

## 6. `ClassCastException` gây nhầm lẫn: “không cast được X sang X”?

Đây là triệu chứng thường gặp trong các môi trường plugin hoặc application server. Một thông báo lỗi có thể trông như:

```text
class com.example.Customer cannot be cast to class com.example.Customer
```

Phần chi tiết bổ sung của JVM có thể đề cập module và loader thực tế. Điều quan trọng là **hai tên hiển thị giống nhau không nhất thiết mô tả cùng kiểu runtime**.

Khi gặp sự cố này, đừng chỉ so `getName()`. Hãy thu thập theo từng object:

```java
Class<?> c = value.getClass();
System.out.println("type=" + c.getName());
System.out.println("loader=" + c.getClassLoader());
System.out.println("module=" + c.getModule());
```

Đây là fragment kiểm tra, giả định `value` khác null. Cần thận trọng khi đưa thông tin này vào log production (không lộ classpath, cấu trúc triển khai hoặc dữ liệu nhạy cảm qua thông báo công khai).

**Mẹo điều tra:** so sánh chính hai đối tượng `Class`, dùng `getClassLoader()` để quan sát defining loader, rồi xác định đường nạp đã chọn. Chuỗi `toString()` của loader là thông tin phụ trợ; không dùng nó thay bằng chứng danh tính object loader.

## 7. Có bắt buộc cùng loader mới giao tiếp được không?

Không. Hai plugin có class nội bộ riêng vẫn có thể phối hợp qua **API dùng chung** được định nghĩa bởi cùng loader cha. Cách minh họa ở phần 4 là `CodeView`:

- `CodeView` được load/định nghĩa bởi lớp cha dùng chung.
- `Value` của `loaderA` và `Value` của `loaderB` đều implements đúng **cùng `CodeView` runtime**.
- Có thể nhận chúng dưới kiểu `CodeView` và gọi `code()` mà không cần cast sang `Value` của plugin khác.

Một thiết kế hệ thống thường đặt interface API, DTO dùng chung hoặc kiểu thông điệp ở tầng classpath/module cha mà các plugin cùng nhìn thấy. Các kiểu implementation riêng của plugin được giữ nội bộ và không rò rỉ qua ranh giới. Khi muốn truyền dữ liệu mà không chia sẻ lớp implementation, có thể dùng interface ổn định, primitive/`String`, hoặc một định dạng serialize có schema rõ ràng.

**Lưu ý:** bản thân việc hai interface có cùng tên chưa đủ. Nếu mỗi loader cũng định nghĩa riêng `com.example.Api`, chúng lại là **hai interface runtime khác nhau**, và phép cast sang interface ở phía kia vẫn thất bại. Phải thật sự chia sẻ **cùng định nghĩa runtime của API**, không chỉ sao chép mã nguồn/JAR.

## 8. Class loader, `equals()` và `hashCode()`

Có hai thiết kế cần phân biệt:

### Bằng nhau theo kiểu thực tế

Một value class có thể yêu cầu `getClass() == other.getClass()` rồi so các trường. Như ví dụ, các instance cùng tên ở loader khác nhau không được xem bằng nhau; điều này tránh ép kiểu sai và phù hợp bản sắc kiểu.

### Bằng nhau theo một giao diện chia sẻ

Một API có thể định nghĩa quan hệ bằng nhau xuyên implementation, nhưng phải đặc biệt thận trọng: cả hai phía phải cùng tuân thủ **đối xứng, bắc cầu, nhất quán và `hashCode()`**.

Ví dụ, nếu một bên so bằng `getClass()` và bên kia so chỉ theo `CodeView.code()`, có thể xảy ra:

```text
a.equals(b) = false
b.equals(a) = true
```

Đó là vi phạm **tính đối xứng** của `equals`. Nếu cần so dữ liệu logic giữa các plugin, một cách an toàn thường là trích ra **khóa bất biến chung** hoặc so các giá trị từ API chung bằng phương thức so sánh riêng, thay vì yêu cầu hai class implementation viết `equals` tương thích xuyên loader.

Không viết kiểu:

```java
// SAI VỀ KIỂM TRA BẢN SẮC KIỂU:
if (other.getClass().getName().equals(getClass().getName())) {
    // Ép kiểu sang class hiện tại KHÔNG an toàn.
}
```

Đây là **fragment cố ý minh họa lỗi**; nó còn cần kiểm tra null. Kết quả trùng tên không chứng minh việc cast được, không chứng minh cấu trúc trường giống nhau và không cho phép coi object là cùng kiểu.

Về `hashCode`, hai đối tượng khác lớp loader có thể có cùng hash dù `equals` khác nhau. Không có yêu cầu “class khác thì hash bắt buộc khác”. Nếu hai đối tượng **được phép bằng nhau theo contract**, lúc đó mới bắt buộc hash bằng nhau.

## 9. Phân biệt class loader với package, JAR và Java module

Không nên nhầm các khái niệm:

| Khái niệm | Ý nghĩa | Có đủ để xác định `Class` runtime không? |
| --- | --- | --- |
| Tên lớp/package | Chuỗi định danh trong bytecode | **Không**, còn defining loader |
| Tên tệp/JAR | Nơi chứa resource hoặc bytecode | **Không**, một JAR có thể được dùng bởi nhiều loader |
| Class loader | Đối tượng tham gia nạp/định nghĩa class | Kết hợp với tên class để xác định kiểu runtime thông thường |
| Java Platform Module System (JPMS) | Mô tả module, khả năng đọc, export/open package | Có ảnh hưởng đến khả năng truy cập/lookup, nhưng không thay thế việc xem danh tính `Class` và defining loader |

Trong các ứng dụng module, module liên quan đến class có thể được quan sát bằng `Class.getModule()`. Không suy luận rằng cùng tên module hoặc cùng tên package đảm bảo cùng `Class`. Và ngược lại, việc thấy các module khác nhau cũng chưa phải lời giải đầy đủ cho một `ClassCastException` mà chưa kiểm tra loader/type thực tế.

### `Class.forName` không luôn tạo lớp mới

`Class.forName(name)` thường dùng loader liên quan đến caller. `Class.forName(name, initialize, loader)` cho phép chỉ định loader yêu cầu nạp. Nhưng loader được chỉ định **có thể ủy quyền**, khiến ta nhận lại class do cha định nghĩa; nó không tự động tạo một bản sao thứ hai.

Ví dụ trên chỉ tạo hai bản vì `IsolatedValueLoader.loadClass` cố ý **tự gọi `defineClass` cho tên mục tiêu**. Với các tên khác, loader vẫn dùng `super.loadClass` và cơ chế ủy quyền thông thường.

## 10. Hệ quả ở reflection, collection và plugin architecture

### Reflection có cần đúng đối tượng `Class`?

Có. Khi tìm constructor/method với tham số kiểu cụ thể, Java reflection làm việc với **kiểu runtime**, không chỉ chuỗi tên. Nếu API yêu cầu `com.example.Customer` do loader cha định nghĩa mà caller cung cấp một `Customer` trùng tên do loader plugin riêng định nghĩa, việc cast hoặc tìm method với kiểu parameter tương ứng có thể thất bại.

Các thông báo như `NoSuchMethodException`, `IllegalArgumentException` khi truyền argument phản chiếu, hoặc `ClassCastException` có thể là triệu chứng của **không khớp kiểu runtime**. Không được giải quyết bằng cách so tên lớp rồi ép cast.

### Collection có tự hợp nhất hai class cùng tên không?

Không. `HashSet` và `HashMap` dùng `equals()`/`hashCode()` của phần tử hoặc khóa; nếu những phương thức ấy phân biệt class loader, hai giá trị cùng tên/cùng dữ liệu có thể là hai khóa khác nhau.

Nếu muốn dùng khóa xuyên ranh giới class loader, hãy dùng kiểu khóa từ API chung (ví dụ `String`, `UUID` hoặc một immutable DTO được định nghĩa chung). Bảo đảm `equals` và `hashCode` của kiểu khóa thống nhất, thay vì dựa trên tên class implementation.

### Class loader và khả năng giải phóng plugin

Các tham chiếu sống đến đối tượng, `Class<?>`, loader, thread context class loader, static cache hoặc registry có thể giữ class loader và các class của nó còn reachable, làm hệ thống không giải phóng được các phiên bản plugin cũ. Khi thiết kế hot reload/unload, cần quản lý lifecycle và loại bỏ tham chiếu giữ loader. Đây là lưu ý vận hành bổ sung, không phải tiêu chí của tính bằng nhau.

## 11. Quy trình chẩn đoán “cùng tên mà cast thất bại”

1. **Lấy đúng hai object/type:** đối tượng thực tế và kiểu đích của phép cast hoặc tham số method.
2. **In `getName()`:** xác nhận tên nhị phân có giống nhau không.
3. **So đối tượng `Class` trực tiếp:** `actualType == expectedType` và, nếu có kế thừa, `expectedType.isAssignableFrom(actualType)`.
4. **Xem `getClassLoader()` và `getModule()`:** ghi nhận defining loader, module và bối cảnh classpath khi cần.
5. **Kiểm tra đường nạp:** parent delegation hay loader riêng, có bản JAR trùng hoặc plugin đóng gói cả shared API không.
6. **Kiểm tra ranh giới API:** kiểu implementation có bị truyền qua một interface/DTO được nạp riêng hai lần không.
7. **Khắc phục ở kiến trúc nạp lớp:** chia sẻ đúng API ở loader chung, tránh đóng gói bản sao shared class trong từng plugin, hoặc chuyển dữ liệu sang giá trị trung gian có schema rõ ràng.
8. **Kiểm tra lại cả cast lẫn `equals`/`hashCode`:** nếu đổi chính sách nạp hoặc kiểu khóa, collection, reflection và kiểm thử tích hợp phải cùng thống nhất.

Fragment chẩn đoán kiểu tương thích:

```java
Class<?> actual = value.getClass();
Class<?> required = SomeApiType.class;

System.out.println(actual.getName());
System.out.println(required.getName());
System.out.println(actual == required);
System.out.println(required.isAssignableFrom(actual));
```

Đây là đoạn minh họa; `value` và `SomeApiType` phải có thật trong code gọi. `isAssignableFrom` xác định khả năng gán kiểu theo runtime type hierarchy, không chỉ tên class.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Hai `Class<?>` có cùng `getName()` nhưng `getClassLoader()` là hai instance khác nhau. Có thể kết luận `Class` của chúng bằng nhau không?

**Đáp án:** Không. Nếu đó là hai **defining loader** thực tế khác nhau cho cùng tên class, chúng là hai kiểu runtime riêng. Còn nếu chỉ biết hai loader được dùng để **yêu cầu nạp**, cả hai có thể ủy quyền về cùng class do cha định nghĩa, nên phải kiểm tra `Class<?>` trả về.

**Câu 2.** Vì sao hai plugin có thể dùng chung một interface nhưng không thể cast trực tiếp implementation của nhau?

**Đáp án:** Cùng interface **do loader chung định nghĩa** là một type runtime duy nhất; mỗi implementation vẫn có thể là một type riêng do loader plugin định nghĩa. Cast tới interface chung hợp lệ, cast sang implementation bản khác không hợp lệ.

**Câu 3.** `getClass().getName().equals(...)` có thay thế an toàn cho `getClass() == ...` trong `equals()` không?

**Đáp án:** Không. Chuỗi tên có thể trùng trong khi type khác loader; dùng tên có thể khiến nhánh cast không an toàn, làm thay đổi ngữ nghĩa và gây `ClassCastException`.

**Câu 4.** Hai object không bằng nhau có thể có cùng `hashCode()` không?

**Đáp án:** Có. Collision là bình thường và không vi phạm hợp đồng. Chỉ khi `equals()` trả `true` thì hash bằng nhau là bắt buộc.

**Câu 5.** `Class.forName(name, true, loaderA)` và cùng lời gọi với `loaderB` chắc chắn trả hai class khác nhau?

**Đáp án:** Không. Nếu cả hai loader ủy quyền cho cùng một defining loader, chúng có thể trả cùng đối tượng `Class`. Phải xem cách loader thực thi.

## Ghi nhớ

**Bản sắc một lớp trong JVM không được quyết định chỉ bằng tên.** Với các class tham chiếu thông thường, tên nhị phân kết hợp **class loader định nghĩa** mới xác định kiểu runtime. Vì vậy các class cùng tên từ loader khác nhau có thể không cast được cho nhau, `instanceof` thất bại và `getClass()` cho hai đối tượng khác nhau. Để tránh lỗi ở hệ thống plugin/module, hãy chia sẻ API chung qua một định nghĩa runtime thống nhất, kiểm tra `Class<?>` và defining loader thay vì chỉ so tên, và tách quan hệ bằng nhau nghiệp vụ khỏi việc nhận diện implementation.
