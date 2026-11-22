# Class.isHidden và nhận diện lớp ẩn trong Java

> **Bối cảnh:** Đây là nội dung về **hidden class** của Java, được chuẩn hóa từ **Java 15** và vẫn là một phần của API chính thức trong các JDK hiện đại (ví dụ Java 17, 21, 25). Bài học tập trung vào `Class.isHidden()`, cách nhận diện chính xác một hidden class và lý do các đặc điểm như “anonymous”, “nested”, “synthetic” hay tên có ký tự đặc biệt không thể thay thế phép kiểm tra này. Ví dụ sử dụng JDK 17 trở lên, không bật preview feature và không dùng các cơ chế tạo lớp đã lỗi thời.

## 1. Hidden class là gì?

**Hidden class (lớp ẩn)** là một lớp hoặc interface được JVM tạo thông qua API `MethodHandles.Lookup.defineHiddenClass(...)`. Nó phục vụ các tình huống cần sinh và sử dụng lớp ở **thời gian chạy** nhưng không cần công bố lớp ấy để các thành phần khác tìm và liên kết theo một **binary name** thông thường.

Một số đặc điểm nền tảng:

1. Hidden class vẫn là **một lớp thực sự** của JVM. Nó có `Class<?>` tương ứng, có thể có trường, phương thức, constructor, kế thừa hoặc triển khai interface theo các quy tắc JVM áp dụng.
2. Hidden class được định nghĩa từ **bytecode ở định dạng class file**, thường do một framework/công cụ sinh ra hoặc cung cấp. Java không có cú pháp nguồn dạng `hidden class Something` để khai báo trực tiếp.
3. Hidden class **không có binary name thông thường** cho việc liên kết tên lớp từ constant pool của các lớp khác. Nó không được tìm bằng `Class.forName(...)` hoặc `ClassLoader.loadClass(...)`.
4. Người tạo lớp nhận một `MethodHandles.Lookup` trỏ tới hidden class; từ đó có thể lấy `Class<?>` qua `lookupClass()` và thao tác bằng các API được phép.
5. Đặc tính “hidden” liên quan tới **khả năng tìm và liên kết danh nghĩa trong JVM**; **không** có nghĩa lớp được mã hóa, bảo mật, vô hình trước debugger hoặc được miễn kiểm tra quyền truy cập.

Hidden class hữu ích cho các công cụ tạo mã tại runtime như một số cơ chế triển khai lambda, ngôn ngữ chạy trên JVM, framework runtime hoặc hệ thống cần nhiều lớp chỉ dùng nội bộ. Việc một nền tảng cụ thể có dùng hidden class hay không là chi tiết triển khai của nền tảng ấy; **không mặc định mọi lambda hay proxy đều là hidden class**.

## 2. API chính thức: `Class.isHidden()`

Trong `java.lang.Class`, phương thức có chữ ký:

```java
public boolean isHidden()
```

`isHidden()` trả `true` **khi và chỉ khi** đối tượng `Class<?>` đại diện cho một hidden class. API này có từ Java 15 và vẫn được hỗ trợ trên JDK hiện hành.

Ví dụ:

```java
Class<?> type = String.class;
boolean hidden = type.isHidden(); // false
```

Ở đây `String.class` là một lớp thông thường, nên kết quả là `false`.

Nếu đã có một đối tượng bất kỳ, có thể lấy `Class<?>` của nó rồi kiểm tra:

```java
static boolean hasHiddenRuntimeClass(Object value) {
    return value != null && value.getClass().isHidden();
}
```

Đoạn trên là **phương thức minh họa** để đặt trong một class. Nó kiểm tra **kiểu runtime trực tiếp** của đối tượng, không kiểm tra kiểu tổng quát được khai báo cho biến. Với `null`, không thể gọi `getClass()`; ví dụ chủ động trả `false` cho đầu vào null.

### Cần nhận diện cái gì?

| Câu hỏi | API phù hợp | Ý nghĩa |
| --- | --- | --- |
| Lớp này thực sự là hidden class? | `clazz.isHidden()` | Tiêu chí trực tiếp và chính thức |
| Đây là lớp khai báo ẩn danh trong mã Java? | `clazz.isAnonymousClass()` | Phân loại **anonymous class**, không phải hidden |
| Đây là lớp lồng bên trong một lớp khác? | `clazz.isMemberClass()` | Phân loại **member class**, không phải hidden |
| Đây là lớp cục bộ trong block/phương thức? | `clazz.isLocalClass()` | Phân loại **local class**, không phải hidden |
| Class có cờ synthetic? | `clazz.isSynthetic()` | Phản ánh cờ synthetic; không đồng nghĩa với hidden |
| Đây có phải array class? | `clazz.isArray()` | Phân biệt array với lớp/interface thông thường |
| Có thể lấy lớp bằng tên binary thông thường? | `Class.forName(name)` | Thực hiện tra cứu theo tên; **không thể tra cứu hidden class** |

**Không xây thuật toán nhận diện hidden class bằng các phép đoán** như `getName().contains("$")`, `isSynthetic()` hoặc `isAnonymousClass()`. Đó là những thuộc tính khác; chúng có thể xuất hiện trong các loại lớp bình thường.

## 3. Hidden khác gì với anonymous, local, nested và private?

Các thuật ngữ dễ bị lẫn:

- **Member/nested class:** là lớp được khai báo bên trong lớp hoặc interface khác, ví dụ `Outer.Inner`. Nó có thể là `private` hoặc `public` nhưng không trở thành hidden chỉ vì nằm bên trong.
- **Local class:** là lớp khai báo bên trong phương thức hoặc block. Có thể không có canonical name, nhưng điều đó **không** làm `isHidden()` thành `true`.
- **Anonymous class:** là lớp được tạo bằng biểu thức như `new Runnable() { ... }`. Đây là một cấu trúc ngôn ngữ Java; class file do `javac` tạo cho anonymous class thông thường vẫn là một lớp **không hidden**.
- **Private/package-private class hay member:** nói về **phạm vi truy cập**, không nói về hidden status.
- **Synthetic:** nói về một thuộc tính của class file/đối tượng reflection, không phải tiêu chí xác định hidden class.
- **Hidden class:** là cách JVM định nghĩa lớp từ bytecode qua `Lookup.defineHiddenClass`, kèm những giới hạn về liên kết tên.

Ví dụ một member class:

```java
public class Outer {
    private static class Inner {
    }

    public static void main(String[] args) {
        System.out.println(Inner.class.isMemberClass());
        System.out.println(Inner.class.isHidden());
    }
}
```

Lưu vào `Outer.java`, chạy `javac Outer.java` rồi `java Outer`. Stdout:

```text
true
false
```

Lớp `Inner` là **member class** của `Outer`, có modifier `private`; nó **không** phải hidden class. Tương tự, một anonymous class trong cú pháp Java thông thường có thể thỏa `isAnonymousClass()==true` mà `isHidden()==false`.

### Không suy luận từ `getCanonicalName() == null`

Một hidden class không có **canonical name**, nên `getCanonicalName()` trả `null`. Tuy nhiên một **local class** và một **anonymous class** cũng không có canonical name. Bởi vậy:

```java
boolean notReliable = clazz.getCanonicalName() == null;
boolean correctCheck = clazz.isHidden();
```

Đoạn này là snippet với biến `clazz` đã được khai báo. `notReliable` không phải phép kiểm tra hidden class; `correctCheck` mới đáp ứng câu hỏi của bài.

## 4. Hidden class được tạo và nhận lại như thế nào?

API quan trọng nằm ở `java.lang.invoke.MethodHandles.Lookup`:

```java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
```

Ý nghĩa chính:

- `bytes`: dữ liệu class file hợp lệ có chứa định nghĩa lớp/interface. **Không** phải source code `.java` hay một mảng ký tự.
- `initialize`: yêu cầu JVM khởi tạo lớp ngay sau khi định nghĩa hay chưa, theo hợp đồng API.
- `options`: tùy chọn như `NESTMATE` và `STRONG`. Nếu không cần tùy chọn, có thể gọi `defineHiddenClass(bytes, true)`.
- Kết quả là một **`Lookup` mới có lookup class là hidden class vừa tạo**. Gọi `lookupClass()` để lấy đối tượng `Class<?>` tương ứng.
- `Lookup` thực hiện kiểm tra đặc quyền; phương thức cần ngữ cảnh lookup có quyền thích hợp, và class file phải thỏa yêu cầu về package/runtime của lookup. Không thể tùy ý nhúng bytecode của bất cứ package nào vào mọi lookup.

Luồng xử lý:

```text
class file bytes
      |
      v
MethodHandles.lookup()
      |
      v
lookup.defineHiddenClass(bytes, initialize, options...)
      |
      v
Lookup của hidden class
      |
      +--> lookupClass() --> Class<?> --> isHidden() == true
      |
      +--> findStatic / findConstructor / ... để dùng thành phần được phép
```

**Lưu ý:** Tạo hidden class từ bytecode không có nghĩa file class nguồn ban đầu cũng trở thành hidden. Nếu có một class thông thường đã được nạp từ đúng bytecode đó, việc định nghĩa thêm một hidden class sẽ tạo một **định danh lớp khác**. JVM phân biệt chúng qua class identity và cách lớp được định nghĩa.

### Khi nào cần quan tâm đến `NESTMATE` và `STRONG`?

Hai tùy chọn chính thức:

| `Lookup.ClassOption` | Tác dụng | Hiểu đúng |
| --- | --- | --- |
| `NESTMATE` | Tạo hidden class như một nestmate của lookup class theo cơ chế nest JVM | Có thể cho phép truy cập `private` giữa các nestmate khi các điều kiện khác được đáp ứng; **không biến hidden class thành member class nguồn** |
| `STRONG` | Ràng buộc vòng đời với defining class loader tương tự lớp thông thường | Nếu **không** chỉ định, hidden class có thể được unload độc lập khi không còn tham chiếu giữ nó sống; không thể dự đoán chính xác thời điểm GC |

Đây là các chi tiết dành cho công cụ sinh mã hoặc framework. Khi chỉ muốn **nhận diện hidden class**, bạn không cần đọc các tùy chọn; `Class.isHidden()` vẫn là phép kiểm tra đúng.

## 5. Ví dụ Java hoàn chỉnh: tạo một hidden class thật

Ví dụ sau sử dụng **một file nguồn** chứa **hai top-level class**: lớp chạy chính và một lớp mẫu package-private. `javac` sẽ tạo ít nhất `HiddenClassDemo.class` và `ClassTemplate.class`. Chương trình đọc `ClassTemplate.class` thành `byte[]` rồi dùng `Lookup.defineHiddenClass` để tạo **một lớp mới thực sự hidden**.

Đặt toàn bộ nội dung sau vào file **`HiddenClassDemo.java`**. Giữ cả hai class **cùng một file** và chạy ở thư mục chứa class file sau khi biên dịch.

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Array;

public class HiddenClassDemo {
    static class MemberExample {
    }

    public static void main(String[] args) throws Throwable {
        // ClassTemplate.class nằm cùng package với HiddenClassDemo.
        byte[] classBytes;
        try (InputStream in = HiddenClassDemo.class
                .getResourceAsStream("ClassTemplate.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Cannot find ClassTemplate.class");
            }
            classBytes = in.readAllBytes();
        }

        Class<?> ordinary = ClassTemplate.class;
        Class<?> member = MemberExample.class;

        Runnable anonymousObject = new Runnable() {
            @Override
            public void run() {
            }
        };
        Class<?> anonymous = anonymousObject.getClass();

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        classBytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println("ordinary.hidden=" + ordinary.isHidden());
        System.out.println("member.hidden=" + member.isHidden());
        System.out.println("member.member=" + member.isMemberClass());
        System.out.println("anonymous.hidden="
                + anonymous.isHidden());
        System.out.println("anonymous.anonymous="
                + anonymous.isAnonymousClass());

        System.out.println("hidden.hidden=" + hidden.isHidden());
        System.out.println("hidden.sameAsOrdinary="
                + (hidden == ordinary));
        System.out.println("hidden.hasSlash="
                + hidden.getName().contains("/"));
        System.out.println("hidden.canonicalNull="
                + (hidden.getCanonicalName() == null));
        System.out.println("hidden.hasNominalDescriptor="
                + hidden.describeConstable().isPresent());

        boolean foundByName;
        try {
            Class.forName(hidden.getName());
            foundByName = true;
        } catch (ClassNotFoundException e) {
            foundByName = false;
        }
        System.out.println("hidden.foundByName=" + foundByName);

        MethodHandle answerMethod = hiddenLookup.findStatic(
                hidden, "answer", MethodType.methodType(int.class));
        int answer = (int) answerMethod.invokeExact();
        System.out.println("hidden.answer=" + answer);

        Class<?> arrayOfHidden =
                Array.newInstance(hidden, 0).getClass();
        System.out.println("array.hidden="
                + arrayOfHidden.isHidden());
        System.out.println("array.component.hidden="
                + arrayOfHidden.getComponentType().isHidden());
        System.out.println("primitive.hidden=" + int.class.isHidden());
    }
}

// Lớp mẫu top-level thông thường, có bytecode để định nghĩa hidden class.
class ClassTemplate {
    static int answer() {
        return 42;
    }
}
```

### Biên dịch và chạy

Ví dụ dùng `InputStream.readAllBytes()` (đã có trong Java hiện đại) và các hidden-class API chuẩn hóa từ Java 15. Sử dụng **JDK 17 trở lên**, chẳng hạn JDK 21 hoặc 25:

```bash
javac -encoding UTF-8 HiddenClassDemo.java
java HiddenClassDemo
```

**Stdout chính xác:**

```text
ordinary.hidden=false
member.hidden=false
member.member=true
anonymous.hidden=false
anonymous.anonymous=true
hidden.hidden=true
hidden.sameAsOrdinary=false
hidden.hasSlash=true
hidden.canonicalNull=true
hidden.hasNominalDescriptor=false
hidden.foundByName=false
hidden.answer=42
array.hidden=false
array.component.hidden=true
primitive.hidden=false
```

### Giải thích các dòng kết quả

1. `ordinary.hidden=false`: `ClassTemplate.class` do `javac` tạo và runtime nạp theo đường thông thường **không hidden**.
2. `member.hidden=false` và `member.member=true`: một class được khai báo **trong** class khác là member class, không phải hidden class chỉ vì lồng nhau.
3. `anonymous.hidden=false` nhưng `anonymous.anonymous=true`: anonymous class trong mã nguồn có cách phân loại riêng.
4. `hidden.hidden=true`: lớp tạo qua `defineHiddenClass` thực sự là hidden class.
5. `hidden.sameAsOrdinary=false`: dù hidden class được tạo từ bytecode của `ClassTemplate`, chúng là hai lớp **khác identity** trong JVM.
6. `hidden.hasSlash=true`: `Class.getName()` của hidden class chứa một dấu `/` phân cách phần tên trong class file và hậu tố do JVM cấp. **Không được hard-code hậu tố** hoặc dựa vào toàn bộ tên động để kiểm thử.
7. `hidden.canonicalNull=true`: hidden class không có canonical name.
8. `hidden.hasNominalDescriptor=false`: `Class.describeConstable()` không thể tạo descriptor danh nghĩa cho hidden class.
9. `hidden.foundByName=false`: `Class.forName(hidden.getName())` không tìm được hidden class. Muốn thao tác với nó, hãy giữ `Lookup`/`Class<?>` do lúc định nghĩa cung cấp.
10. `hidden.answer=42`: hidden class vẫn có phương thức thực thi được. `MethodHandle` được tạo qua lookup của hidden class cho phép gọi phương thức `answer` trong ví dụ.
11. `array.hidden=false` nhưng `array.component.hidden=true`: **array class** chứa phần tử có kiểu hidden không tự trở thành hidden class; cần kiểm tra `getComponentType()` khi muốn biết kiểu phần tử.
12. `primitive.hidden=false`: `int.class` không biểu diễn hidden class.

**Điểm quan trọng:** Chương trình **không** in tên hidden class đầy đủ vì phần hậu tố do runtime sinh ra thay đổi theo lần chạy/môi trường. Việc xuất các boolean có quy tắc cố định giúp stdout có thể kiểm tra chính xác.

### Nếu gặp lỗi đọc class file

Thông báo `Cannot find ClassTemplate.class` cho biết chương trình không tìm thấy **resource** mà nó cần. Đảm bảo:

- Chạy `javac HiddenClassDemo.java` để tạo cả `HiddenClassDemo.class` và `ClassTemplate.class`.
- Chạy với classpath gồm thư mục chứa các file `.class`, ví dụ mở terminal trong cùng thư mục rồi gọi `java HiddenClassDemo`.
- Giữ `HiddenClassDemo` và `ClassTemplate` cùng một package. Ví dụ trên dùng **unnamed package** cho mục đích học tập, nên không cần tạo file package phức tạp.
- Nếu chuyển bài vào project có package, giữ resource path tương ứng và đặt class mẫu cùng runtime package với lookup class. Nếu đóng gói thành JAR, bảo đảm class file mẫu cũng nằm trong artifact.

Ví dụ này sử dụng bytecode từ file class mẫu do bạn vừa biên dịch, không cần thư viện sinh bytecode bên ngoài.

## 6. Vì sao không dùng `Class.forName` để nhận diện hidden class?

`Class.forName(String)` được thiết kế để **tìm lớp theo binary name** bằng class loader. Hidden class được định nghĩa để **không tham gia cơ chế tìm kiếm danh nghĩa đó**.

Với lớp thông thường:

```java
Class<?> ordinary = Class.forName("java.lang.String");
System.out.println(ordinary == String.class); // true
```

Với hidden class tạo trong chương trình ở trên:

```java
// hidden là Class<?> nhận từ hiddenLookup.lookupClass().
Class.forName(hidden.getName()); // không tìm được hidden class
```

Dòng thứ hai là **đoạn minh họa cố ý gây ClassNotFoundException**; không phải đoạn mã nên gọi trần mà không xử lý ngoại lệ.

Sự khác nhau cần nhớ:

| Đối tượng | Có `Class<?>`? | `isHidden()` | `Class.forName(getName())` |
| --- | --- | --- | --- |
| `String.class` | Có | `false` | Tìm được |
| Member class thông thường | Có | `false` | Có thể tìm theo binary name phù hợp |
| Anonymous class do `javac` tạo theo cú pháp Java | Có | `false` | Không dùng nó làm tiêu chí xác định hidden |
| Hidden class qua `defineHiddenClass` | Có | `true` | **Không tìm được** |
| Array của hidden class | Có | `false` | Không tìm được array đó bằng tên; kiểu phần tử vẫn hidden |
| Primitive type như `int.class` | Có | `false` | Không dùng tên primitive `"int"` như một binary name |

**Không lập luận đảo chiều:** `Class.forName(...)` thất bại **không chứng minh** đó là hidden class; nó còn thất bại khi tên sai, lớp thiếu khỏi classpath, class loader không biết lớp, v.v. Chỉ `Class.isHidden()` trên đối tượng `Class<?>` hiện có mới trả lời trực tiếp câu hỏi.

## 7. Các API tên lớp: thông tin nào có thể tin?

`Class<?>` có nhiều phương thức trả thông tin tên, nhưng hidden class có quy tắc riêng.

### `getName()`

Theo đặc tả `Class.getName()`, với hidden class, kết quả có dạng:

```text
N + "/" + suffix
```

Trong đó `N` là binary name được chỉ ra bởi bytecode nguồn và `suffix` do JVM cấp. Ví dụ trong một bản chạy có thể trông như:

```text
ClassTemplate/0x0000000800c00400
```

Đó **chỉ là một ví dụ minh họa**, không phải chuỗi phải xuất hiện đúng trong mọi lần chạy hoặc mọi JVM. Hậu tố không ổn định và **không phải tên để `Class.forName` sử dụng**.

### `getCanonicalName()`

`hidden.getCanonicalName()` trả `null`. Nhưng `getCanonicalName()==null` **không đủ** để nhận diện hidden, bởi local và anonymous class cũng không có canonical name.

### `describeConstable()` và `descriptorString()`

- Hidden class không có **nominal descriptor**; vì thế `hidden.describeConstable()` trả `Optional.empty()`.
- `Class.descriptorString()` của hidden class có thể cung cấp chuỗi thông tin chứa tên đặc biệt và hậu tố, nhưng đặc tả nói chuỗi đó **không phải field descriptor thông thường** có thể dùng để mô tả tên lớp theo cách danh nghĩa.
- Không cố tái tạo `ClassDesc` từ tên hidden class để lấy lại lớp bằng tên; đó đi ngược mục đích thiết kế của hidden class.

| API | Dùng để làm gì? | Có nên dùng để quyết định hidden? |
| --- | --- | --- |
| `isHidden()` | Nhận diện hidden class thực sự | **Có, là lựa chọn chính thức** |
| `getName()` | Cung cấp thông tin tên runtime | Không; có hậu tố động |
| `getCanonicalName()` | Cung cấp canonical name nếu có | Không; nhiều loại class khác cũng `null` |
| `describeConstable()` | Thử tạo nominal descriptor | Có liên quan về mặt ngữ nghĩa, nhưng không thay thế `isHidden()` để phân loại |
| `isSynthetic()` | Kiểm tra cờ synthetic của class | Không; là thuộc tính khác |

## 8. Array có phần tử hidden: trường hợp dễ bỏ sót

Theo tài liệu Java, một **hidden class không phải một array class**, nhưng nó **có thể là kiểu phần tử của một array**.

```java
Class<?> hiddenType = hiddenLookup.lookupClass();
Class<?> oneDimension =
        java.lang.reflect.Array.newInstance(hiddenType, 0).getClass();
```

Đây là snippet giả định đã có `hiddenLookup` từ `defineHiddenClass` như chương trình hoàn chỉnh.

Kết quả:

- `hiddenType.isHidden()` → `true`.
- `oneDimension.isHidden()` → `false`.
- `oneDimension.isArray()` → `true`.
- `oneDimension.getComponentType().isHidden()` → `true`.

Nếu bài toán muốn biết “kiểu này **hoặc kiểu phần tử sâu nhất** của array có hidden không?”, có thể duyệt qua thành phần:

```java
static boolean hasHiddenElementType(Class<?> type) {
    while (type.isArray()) {
        type = type.getComponentType();
    }
    return type.isHidden();
}
```

Đây là **phương thức minh họa** đặt bên trong class, giả định `type` không `null`.

Tên phương thức được chọn có chủ đích: nó kiểm tra hidden ở **kiểu phần tử sau cùng**, không khẳng định chính array class là hidden. Với `String[]` hoặc `int[][]`, kết quả là `false`; với `hiddenType[]`, kết quả là `true`.

Lưu ý kiểu phần tử hidden cũng không khiến array của nó có binary name thông thường có thể nạp bằng `Class.forName`.

## 9. Vòng đời lớp ẩn và tùy chọn `STRONG`

Hidden class được tạo để hỗ trợ các mô hình sinh lớp động, nơi có thể có **nhiều** lớp tạm thời.

- Với hidden class **mặc định** (không có `STRONG`), JVM có thể unload lớp khi không còn những tham chiếu giữ nó sống, **dù defining class loader còn sống**.
- Khi chọn `ClassOption.STRONG`, vòng đời của hidden class được ràng buộc mạnh với defining class loader tương tự lớp thường. Khi loader còn được giữ sống, hidden class không tự unload theo kiểu yếu.
- Đó là chính sách vòng đời, **không** có tác dụng làm `isHidden()` đổi từ `true` thành `false`.
- Garbage collection/class unloading là hành vi phụ thuộc runtime; **không viết test** kỳ vọng lớp ẩn chắc chắn được unload ngay sau một thao tác cụ thể.

Snippet ý tưởng cho người xây framework:

```java
MethodHandles.Lookup strongHidden =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.STRONG);
```

Đây là **snippet cần có hai biến `lookup` và `classBytes` hợp lệ**, không phải chương trình độc lập. Dùng `STRONG` khi kiến trúc thật sự cần vòng đời mạnh; không bật chỉ để kiểm tra hidden.

Tương tự, `NESTMATE` không thay đổi khả năng tìm theo tên của hidden class. Nó chỉ xác định quan hệ nest và quyền truy cập theo quy tắc JVM.

## 10. Khi nào `isHidden()` hữu ích trong ứng dụng?

### Phân tích runtime và công cụ chẩn đoán

Khi nhận một đối tượng `Class<?>` từ framework, bạn có thể phân loại thông tin trước khi ghi log hay dùng reflection:

```java
static String classify(Class<?> type) {
    if (type.isHidden()) {
        return "hidden";
    }
    if (type.isArray()) {
        return "array";
    }
    if (type.isAnonymousClass()) {
        return "anonymous";
    }
    if (type.isLocalClass()) {
        return "local";
    }
    if (type.isMemberClass()) {
        return "member";
    }
    return "ordinary-or-other";
}
```

Đây là **phương thức minh họa**, không phải hệ thống phân loại toàn bộ loại class của Java. Thứ tự các nhánh thể hiện ưu tiên của báo cáo, không có nghĩa các thuộc tính là một phân hoạch toán học hoàn toàn độc lập. Đừng cố ép một runtime class vào một loại bằng cách phân tích chuỗi tên của nó.

### Công cụ sinh mã động

Một hệ thống tạo method handle hoặc bytecode có thể giữ `Lookup` trên lớp đã định nghĩa và dùng `isHidden()` như một kiểm tra sau khi tạo lớp. Việc giữ đúng `Class<?>`/`Lookup` giúp nó thao tác trực tiếp mà không cần tra cứu lớp theo tên.

### Kiểm thử hành vi nội bộ

Với một framework mà **hợp đồng công khai** quy định nó phải tạo hidden class, test có thể kiểm tra `generatedClass.isHidden()`. Tuy nhiên, không nên viết test cứng rằng **mọi biểu thức lambda** hay **mọi proxy** đều được triển khai bằng hidden class: đây có thể là chi tiết thay đổi giữa runtime, phiên bản hoặc chiến lược biên dịch.

### Không dùng như cơ chế bảo mật

Hidden class **không phải sandbox**. Có `Class<?>` hoặc `Lookup` thích hợp thì code vẫn có thể xem hoặc dùng metadata/method theo quyền được cấp. Cần kiểm soát đầu vào bytecode, capability `Lookup`, quyền truy cập và module/class loader như các thành phần thiết kế độc lập.

## 11. Các lỗi và hiểu lầm phổ biến

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `isAnonymousClass()==true` nghĩa là hidden | Anonymous là khái niệm khai báo Java, hidden là cơ chế tạo lớp của JVM | Dùng `isHidden()` |
| Lớp `private static class` là hidden | `private` và nested chỉ liên quan phạm vi truy cập/cấu trúc nguồn | Kiểm tra `isHidden()` riêng |
| Có dấu `$` trong `getName()` là hidden | Tên nested/anonymous thông thường có thể chứa `$` | Không suy đoán từ tên |
| `getCanonicalName()==null` chứng minh hidden | Anonymous và local class cũng thường trả `null` | Dùng `isHidden()` |
| `Class.forName(...)` lỗi thì chắc là hidden | Có nhiều nguyên nhân khác khiến tìm tên thất bại | Giữ `Class<?>` thật và gọi `isHidden()` |
| Có thể dùng `Class.forName(hidden.getName())` | Tên hidden không phải binary name để tra cứu như lớp thường | Dùng `Lookup.lookupClass()` và giữ tham chiếu |
| Array của hidden class cũng hidden | `isHidden()` trên array class trả `false` | Kiểm tra `getComponentType()` nếu cần |
| Lấy tên hidden rồi lưu như mã định danh bền vững | Hậu tố tên được runtime cấp, không có tính ổn định cho thao tác tìm tên | Lưu thông tin riêng của ứng dụng, không dựa vào tên runtime |
| Cứ gọi `defineHiddenClass` là có quyền truy cập mọi package | Lookup có phạm vi quyền; bytecode phải phù hợp runtime package và cấu trúc class file | Dùng lookup có đặc quyền phù hợp, bytecode hợp lệ |
| Hidden class bắt buộc sống cùng class loader | Mặc định nó có thể unload độc lập; `STRONG` thay đổi quan hệ vòng đời | Chọn vòng đời theo thiết kế và tránh kiểm thử thời điểm GC |
| `isHidden()` bảo đảm mã không bị nhìn thấy | Hidden chỉ liên quan liên kết/tìm theo tên | Áp dụng cơ chế bảo mật thông thường riêng biệt |
| In tên động rồi kiểm thử chuỗi tên đúng 100% | Hậu tố có thể thay đổi mỗi lần | Kiểm tra boolean/đặc điểm được đặc tả thay vì hard-code hậu tố |

### Một số lỗi khi dùng `defineHiddenClass`

- **Không có file class mẫu:** `getResourceAsStream(...)` trả `null`. Kiểm tra tài nguyên và classpath.
- **Bytecode không hợp lệ:** class file bị lỗi, định dạng sai hoặc không đáp ứng quy tắc của JVM; xem thông báo lỗi thật từ runtime.
- **Lookup không đủ quyền:** có thể nhận `IllegalAccessException`; phải cung cấp đúng lookup theo thiết kế quyền truy cập.
- **Package không trùng:** class file có package không phù hợp lookup; chỉnh đúng package nguồn và cách tạo bytecode, không tìm cách dùng quyền không liên quan để vượt qua.
- **Tạo nhầm class thường:** gọi `ClassLoader.defineClass` hoặc nạp file class qua classpath không mang nghĩa tạo hidden class. Nếu muốn hidden, dùng đúng `Lookup.defineHiddenClass`.
- **Assumption về class identity:** cùng bytecode không bảo đảm cùng `Class<?>`; mỗi lời gọi tạo hidden class có thể tạo class identity riêng.

## 12. Bài tập tự kiểm tra có đáp án

**Bài 1.** Cho `String.class`, `int.class`, `String[].class`. `isHidden()` có trả `true` cho kiểu nào?

**Đáp án:** Không kiểu nào. Cả ba lần gọi đều cho `false`.

**Bài 2.** Một lớp được khai báo `private static class Helper` bên trong lớp khác có `isHidden()==true` không?

**Đáp án:** Không chỉ vì `private static`. Nó là member class; `isHidden()` chỉ đúng nếu runtime class cụ thể thực sự được định nghĩa như hidden class.

**Bài 3.** Vì sao `hidden.getCanonicalName()==null` chưa đủ làm phép nhận diện?

**Đáp án:** Vì local và anonymous class cũng có thể không có canonical name. Phải dùng `hidden.isHidden()`.

**Bài 4.** Một `Lookup.defineHiddenClass(bytes, true)` trả về kiểu gì và lấy đối tượng lớp bằng gì?

**Đáp án:** Trả `MethodHandles.Lookup`; gọi `lookupClass()` trên lookup ấy để lấy `Class<?>` đại diện cho hidden class.

**Bài 5.** Hidden class tạo từ bytecode của `ClassTemplate.class` có bằng `ClassTemplate.class` khi so sánh identity bằng `==` không?

**Đáp án:** Không. Chúng là hai class identity khác nhau, dù nguồn bytecode có thể xuất phát từ cùng một class file.

**Bài 6.** Có thể dùng `Class.forName(hidden.getName())` để lấy lại hidden class không?

**Đáp án:** Không. Hidden class không được tìm theo binary name qua `Class.forName` hoặc `ClassLoader.loadClass`; giữ `Class<?>` và `Lookup` từ thời điểm định nghĩa.

**Bài 7.** Một array có kiểu phần tử hidden. Giá trị `arrayClass.isHidden()` và `arrayClass.getComponentType().isHidden()` là gì?

**Đáp án:** `false` và `true`. Array class không tự là hidden class, nhưng thành phần có thể hidden.

**Bài 8.** `ClassOption.STRONG` có khiến `isHidden()` trả `false` không?

**Đáp án:** Không. Nó chỉ thay đổi quan hệ vòng đời/unloading với class loader, không thay đổi bản chất hidden class.

### Checklist

- [ ] Tôi hiểu hidden class là một lớp JVM được định nghĩa qua `Lookup.defineHiddenClass(...)`.
- [ ] Tôi dùng `Class.isHidden()` để **nhận diện trực tiếp**, không suy đoán qua tên hoặc thuộc tính khác.
- [ ] Tôi phân biệt hidden với anonymous, member, local, private và synthetic.
- [ ] Tôi biết nhận `Class<?>` của hidden class qua `Lookup.lookupClass()`.
- [ ] Tôi hiểu tại sao `Class.forName(hidden.getName())` không tìm được lớp ẩn.
- [ ] Tôi hiểu tên có hậu tố động, không nên lưu/hard-code làm định danh.
- [ ] Tôi biết hidden class có thể là kiểu phần tử của array nhưng array class không hidden.
- [ ] Tôi hiểu `NESTMATE`, `STRONG` ở mức sử dụng, không nhầm chúng với `isHidden()`.
- [ ] Tôi có thể biên dịch, chạy ví dụ và giải thích từng dòng stdout.

## Nguồn tài liệu chính thức

1. [Oracle Java SE 25 — `Class` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `isHidden()`, mục **Hidden Classes**, `getName()`, `getCanonicalName()`, `describeConstable()`, array class.
2. [Oracle Java SE 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass(byte[], boolean, ClassOption...)`, trả `Lookup` và yêu cầu quyền truy cập.
3. [Oracle Java SE 25 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): ý nghĩa `NESTMATE` và `STRONG`.
4. [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế đã được triển khai chính thức từ Java 15, động cơ và quy tắc về tên/khả năng nạp.
5. [Java Virtual Machine Specification 25](https://docs.oracle.com/javase/specs/jvms/se25/html/index.html): class file, định danh kiểu và quy tắc liên kết JVM.

**Ghi nhớ:** `Class.isHidden()` là phép kiểm tra chuẩn xác cho **runtime class thực sự ẩn**. Tên động, `private`, anonymous/local/member hay synthetic không phải dấu hiệu tương đương. Muốn thử trên thực tế, tạo hidden class qua `MethodHandles.Lookup.defineHiddenClass`, giữ `Lookup` của lớp đó và kiểm tra `lookupClass().isHidden()`.