# Tên runtime, binary name và descriptor của hidden class (Java 15+)

> **Chủ đề cha: Hidden class.** Java 15 giới thiệu *hidden classes* qua JEP 371. Một hidden class có đối tượng `Class<?>`, có thể được thực thi và phản chiếu (reflection), nhưng **không có binary name hợp lệ để các lớp khác tham chiếu theo tên**. Vì vậy, chuỗi từ `Class.getName()` và `Class.descriptorString()` của hidden class có quy tắc đặc biệt. Đây là cơ chế vẫn được hỗ trợ trong JDK hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **tên trong Java source**, **canonical name**, **binary name**, **internal name**, **runtime name** và **type descriptor**.
2. Giải thích vì sao hidden class có `getName()` nhưng **không có binary name hợp lệ**.
3. Nhận biết dạng `N + "/" + suffix` của `Class.getName()` đối với hidden class và dạng `"L" + N_internal + "." + suffix + ";"` của `descriptorString()`.
4. Hiểu tại sao `Class.forName()`, `ClassLoader.loadClass()` và `ClassDesc.ofDescriptor()` không thể tra cứu/mô tả hidden class theo tên đó.
5. Viết chương trình Java 17+ dùng `MethodHandles.Lookup.defineHiddenClass()` và kiểm tra hành vi bằng những mệnh đề có kết quả xác định, không hardcode hậu tố do JVM sinh.
6. Chọn cách nhận diện, lưu tham chiếu và ghi log hidden class phù hợp trong mã ứng dụng hoặc framework.

## 1. Bốn khái niệm dễ bị nhầm

### 1.1. Tên trong source và canonical name

Trong Java source, bạn có thể viết tên lớp `java.util.Map.Entry` hay `edu.hidden.HiddenNamesDemo.Payload`. Với một lớp thành viên (member class) như `Payload`, dấu chấm phân tách tên trong cách viết canonical.

`Class.getCanonicalName()` trả về tên canonical nếu loại đó có canonical name. Một **hidden class không có canonical name**, nên `hidden.getCanonicalName() == null`.

Không suy ra rằng mọi lớp có `getCanonicalName() == null` đều là hidden class: local classes và anonymous classes cũng có thể không có canonical name. Để phát hiện đúng trường hợp hidden, dùng `Class.isHidden()`.

### 1.2. Binary name

*Binary name* theo Java Language Specification là cách định danh có thể dùng trong các tham chiếu danh nghĩa (*nominal references*) của JVM đối với lớp thông thường.

Ví dụ:

| Loại lớp thông thường | Canonical name | Binary name từ `getName()` |
| --- | --- | --- |
| Top-level `String` | `java.lang.String` | `java.lang.String` |
| Member class `Map.Entry` | `java.util.Map.Entry` | `java.util.Map$Entry` |
| Member class `HiddenNamesDemo.Payload` trong package `edu.hidden` | `edu.hidden.HiddenNamesDemo.Payload` | `edu.hidden.HiddenNamesDemo$Payload` |

Dấu `$` trong binary name thường biểu diễn ranh giới lớp lồng được trình biên dịch tạo. Dấu `$` **không tự chứng minh** một lớp là hidden; lớp lồng thông thường vẫn có binary name hợp lệ.

### 1.3. Internal name (dạng JVM trong class file)

JVM dùng *internal form* cho binary name trong nhiều cấu trúc của class file: dấu chấm phân cách **package** chuyển thành dấu gạch chéo `/`.

Ví dụ:

~~~text
Binary:    edu.hidden.HiddenNamesDemo$Payload
Internal:  edu/hidden/HiddenNamesDemo$Payload

Binary:    java.lang.String
Internal:  java/lang/String
~~~

Dấu `/` trong **internal name của một lớp thông thường** phân tách các thành phần package. Điều này **khác** dấu `/` đặc biệt xuất hiện ở **cuối runtime name của hidden class** sau tên binary gốc.

### 1.4. Descriptor (mô tả kiểu theo JVM)

JVM dùng descriptor để diễn tả các kiểu của field và phương thức. Ví dụ:

| Kiểu | Field/type descriptor |
| --- | --- |
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `java.lang.String` | `Ljava/lang/String;` |
| `java.lang.String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |
| `edu.hidden.HiddenNamesDemo.Payload` | `Ledu/hidden/HiddenNamesDemo$Payload;` |

Method descriptor đặt các descriptor của tham số trong `(...)`, sau đó là kiểu trả về. Chẳng hạn phương thức nhận `String` và `int`, trả về `void` có descriptor:

~~~text
(Ljava/lang/String;I)V
~~~

**Lưu ý:** `Class.getName()` của một **array class** có dạng riêng (ví dụ `[Ljava.lang.String;`), không hoàn toàn giống `Class.descriptorString()` của array (`[Ljava/lang/String;`). Vì vậy, không chuyển đổi giữa tên và descriptor bằng cách thay ký tự tùy ý.

## 2. Hidden class có tên runtime nhưng không có binary name hợp lệ

### 2.1. Hidden class là gì trong phạm vi bài này?

`MethodHandles.Lookup.defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` định nghĩa một hidden class từ class-file bytes và trả về một `Lookup` có lookup class là hidden class mới. API này xuất hiện trong Java 15 và vẫn là API hiện hành.

Một số đặc điểm liên quan trực tiếp đến tên:

- Hidden class có `Class<?>` để sử dụng trong chương trình và reflection.
- Nó **không thể được tham chiếu bằng một binary name** trong constant pool của lớp khác.
- `Class.forName()` hoặc `ClassLoader.loadClass()` không tìm được hidden class bằng chuỗi tên runtime.
- `Class.isHidden()` trả về `true` cho hidden class. Đây là cách kiểm tra rõ ràng hơn việc tìm chuỗi `/0x` trong tên.
- Hidden class được định nghĩa trong **runtime package**, module và protection domain tương ứng với lookup class đã dùng để định nghĩa nó; không cần đặt vào một package đặc biệt chỉ vì tên có suffix.
- `defineHiddenClass()` cần `Lookup` có full privilege access và class-file bytes phù hợp với package của lookup class. Không phải lấy một `publicLookup()` tùy ý rồi có thể tạo hidden class trong package nào cũng được.

Hidden class phục vụ các tình huống triển khai lớp runtime mà không muốn lớp đó được tìm thấy qua cơ chế tra cứu danh nghĩa bằng tên, chẳng hạn code generation và language runtime. Việc “hidden” **không có nghĩa** class hoàn toàn vô hình với code đã giữ `Class<?>` hoặc `Lookup` của nó.

### 2.2. Dạng runtime name

Giả sử class-file bytes khai báo tên nội bộ:

~~~text
edu/hidden/HiddenNamesDemo$Payload
~~~

Gọi `defineHiddenClass()` sẽ khiến JVM tạo **runtime name** có dạng:

~~~text
N_binary + "/" + suffix

Ví dụ minh họa:
edu.hidden.HiddenNamesDemo$Payload/0x0000000800ABC000
~~~

`N_binary` là binary name **gốc** biểu diễn bởi class file đã truyền vào; `suffix` là tên không đủ điều kiện (*unqualified name*) do VM bổ sung. Tên chính xác, đặc biệt chuỗi số sau `/`, là **dữ liệu do JVM sinh**; không nên ghi cứng nó trong test, giao thức hay cấu hình.

`hidden.getName()` trả về runtime name dạng trên. Do chứa dấu `/` ở vị trí không được chấp nhận trong Java binary name, toàn bộ chuỗi **không phải binary name**. Đây là khác biệt cốt lõi với một lớp thông thường có `getName()` trả về binary name.

**Không nên:**

~~~java
// Minh họa lỗi thiết kế, không phải chương trình độc lập.
String name = hiddenClass.getName();
Class<?> again = Class.forName(name); // ClassNotFoundException
~~~

**Nên:** Khi cần tham chiếu tới chính hidden class đó, giữ `Class<?>` hoặc `Lookup` / `MethodHandle` thích hợp. Khi ghi log, có thể in `getName()` để hỗ trợ chẩn đoán, nhưng đừng coi chuỗi ấy là một danh tính có thể nạp lại sau lần chạy khác.

## 3. Descriptor của hidden class: nhìn giống descriptor, nhưng không hợp lệ theo JVMS

### 3.1. `Class.descriptorString()` hoạt động thế nào?

Đối với lớp thông thường:

~~~text
Binary:         edu.hidden.HiddenNamesDemo$Payload
Internal:       edu/hidden/HiddenNamesDemo$Payload
Field descriptor: Ledu/hidden/HiddenNamesDemo$Payload;
~~~

Đối với **hidden class** định nghĩa từ cùng class-file bytes, `Class.descriptorString()` trả về một chuỗi đặc biệt:

~~~text
"L" + N_internal + "." + suffix + ";"

Ví dụ minh họa:
Ledu/hidden/HiddenNamesDemo$Payload.0x0000000800ABC000;
~~~

**Dấu chấm `.` trước `suffix` làm cho chuỗi này không phải field/type descriptor hợp lệ theo JVMS `4.3.2`.** Đây là **chuỗi mô tả phục vụ runtime/diagnostics**, không phải một danh tính kiểu có thể nhúng lại trong constant pool để liên kết lớp.

Do đó:

- `hidden.descriptorString()` **vẫn trả về `String`** và hữu ích để kiểm tra/ghi log.
- `hidden.describeConstable()` trả về `Optional.empty()` vì hidden class không có **nominal descriptor**.
- Không truyền chuỗi `hidden.descriptorString()` vào `ClassDesc.ofDescriptor()` rồi mong nhận `ClassDesc` hợp lệ; dạng này bị từ chối.
- Tương tự, `MethodType.descriptorString()` có thể trả về chuỗi **không phải method descriptor JVMS hợp lệ** khi chữ ký chứa hidden class. Không coi mọi chuỗi `descriptorString()` là một descriptor có thể resolve thành type bằng tên.

Một `ClassDesc` mô tả kiểu **theo danh nghĩa** (*nominally*): nó phải có tên/descriptor hợp lệ để có thể được giải quyết trong ngữ cảnh phù hợp. Hidden class cố ý không thỏa điều kiện đó.

### 3.2. So sánh hành vi của các API

| API / thuộc tính | Lớp thông thường | Hidden class |
| --- | --- | --- |
| `Class.isHidden()` | `false` | `true` |
| `Class.getName()` | Binary name hợp lệ, ví dụ `edu.hidden.Foo` | `N + "/" + suffix`, **không phải binary name** |
| `Class.getCanonicalName()` | Có thể có tên canonical | `null` |
| `Class.descriptorString()` | Descriptor JVM hợp lệ | Chuỗi `L... .suffix;`, **không phải descriptor JVM** |
| `Class.describeConstable()` | Thường có `ClassDesc` cho kiểu danh nghĩa | `Optional.empty()` |
| `Class.forName(name)` | Có thể tra cứu theo binary name | Không tra cứu hidden class bằng runtime name |
| `ClassLoader.loadClass(name)` | Có thể tra cứu lớp thông thường | Không tra cứu hidden class theo runtime name |
| `Class.getPackageName()` | Package của lớp | Package runtime bình thường của hidden class |
| Giữ `Class<?>` trực tiếp | Có thể | **Có thể**: đây là cách thao tác với class khi đã được định nghĩa |

Đối với các lớp thông thường, việc một `ClassDesc` có thể được tạo không tự bảo đảm mọi lookup đều có quyền truy cập hoặc resolve thành công. Đối với hidden class, vấn đề cơ bản hơn: **không có descriptor danh nghĩa để resolve theo tên**.

## 4. Ví dụ độc lập: quan sát runtime name của hidden class

Ví dụ dùng Java **17+**, không có thư viện ngoài. Để đơn giản và có class-file bytes thật, chương trình khai báo một member class `Payload` rồi đọc chính file `.class` của nó làm **mẫu bytes** cho `defineHiddenClass()`. Cả lớp chủ và `Payload` đều thuộc package `edu.hidden`, phù hợp điều kiện package của `MethodHandles.lookup()`.

### 4.1. Tạo tệp và biên dịch

Tạo tệp ở:

~~~text
src/edu/hidden/HiddenNamesDemo.java
~~~

**Nội dung đầy đủ:**

~~~java
package edu.hidden;

import java.io.InputStream;
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodHandles;

public class HiddenNamesDemo {
    static class Payload {}

    public static void main(String[] args) throws Exception {
        // Đọc .class bytes của một member class đã biên dịch.
        byte[] bytes;
        try (InputStream in = Payload.class.getResourceAsStream(
                "HiddenNamesDemo$Payload.class")) {
            if (in == null) {
                throw new IllegalStateException(
                    "Missing Payload.class resource");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Class<?> first = lookup.defineHiddenClass(
                bytes, false).lookupClass();
        Class<?> second = lookup.defineHiddenClass(
                bytes, false).lookupClass();

        // Thông tin ổn định của lớp thông thường.
        System.out.println("normalName="
                + Payload.class.getName());
        System.out.println("normalCanonical="
                + Payload.class.getCanonicalName());
        System.out.println("normalDescriptor="
                + Payload.class.descriptorString());
        System.out.println("normalNominal="
                + Payload.class.describeConstable().isPresent());

        // Không in nguyên suffix; kiểm tra hình dạng có ý nghĩa.
        System.out.println("hidden=" + first.isHidden());
        System.out.println("runtimeNamePrefix="
                + first.getName().startsWith(
                    Payload.class.getName() + "/"));
        System.out.println("descriptorPrefix="
                + first.descriptorString().startsWith(
                    "Ledu/hidden/HiddenNamesDemo$Payload."));
        System.out.println("descriptorSemicolon="
                + first.descriptorString().endsWith(";"));
        System.out.println("canonicalMissing="
                + (first.getCanonicalName() == null));
        System.out.println("nominalMissing="
                + first.describeConstable().isEmpty());
        System.out.println("package="
                + first.getPackageName());

        // Mỗi lần defineHiddenClass tạo một hidden class khác.
        System.out.println("differentRuntimeNames="
                + !first.getName().equals(second.getName()));
        System.out.println("differentClassObjects="
                + (first != second));
        System.out.println("sameLoader="
                + (first.getClassLoader() == second.getClassLoader()));
        System.out.println("hiddenNameContainsSlash="
                + first.getName().contains("/"));

        // Không thể tìm hidden class qua binary-name lookup.
        try {
            Class.forName(first.getName());
            System.out.println("lookupByName=found");
        } catch (ClassNotFoundException expected) {
            System.out.println("lookupByName=not-found");
        }

        // Chuỗi descriptor của hidden class không hợp lệ
        // cho một nominal ClassDesc theo JVMS.
        try {
            ClassDesc.ofDescriptor(first.descriptorString());
            System.out.println("nominalDescriptor=accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("nominalDescriptor=rejected");
        }

        // Array class không hidden, dù phần tử là hidden.
        Class<?> array = first.arrayType();
        System.out.println("arrayHidden=" + array.isHidden());
        System.out.println("arrayComponentSame="
                + (array.getComponentType() == first));
        System.out.println("arrayNominalMissing="
                + array.describeConstable().isEmpty());
    }
}
~~~

Chạy từ thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/edu/hidden/HiddenNamesDemo.java
java -cp out edu.hidden.HiddenNamesDemo
~~~

**Kết quả xác định** (đã đối chiếu khi chạy trên JDK 24):

~~~text
normalName=edu.hidden.HiddenNamesDemo$Payload
normalCanonical=edu.hidden.HiddenNamesDemo.Payload
normalDescriptor=Ledu/hidden/HiddenNamesDemo$Payload;
normalNominal=true
hidden=true
runtimeNamePrefix=true
descriptorPrefix=true
descriptorSemicolon=true
canonicalMissing=true
nominalMissing=true
package=edu.hidden
differentRuntimeNames=true
differentClassObjects=true
sameLoader=true
hiddenNameContainsSlash=true
lookupByName=not-found
nominalDescriptor=rejected
arrayHidden=false
arrayComponentSame=true
arrayNominalMissing=true
~~~

Lưu ý về thao tác chạy: `javac -d out` sinh cả `HiddenNamesDemo.class` và `HiddenNamesDemo$Payload.class` vào `out/edu/hidden/`. Classpath `out` làm cho lời gọi `getResourceAsStream("HiddenNamesDemo$Payload.class")` tìm đúng file bytes. Nếu chỉ sao chép file chính mà bỏ file `Payload.class`, chương trình cố ý ném `IllegalStateException` với thông báo rõ ràng.

### 4.2. Giải thích từng nhóm kết quả

**Tên lớp thông thường:** `Payload.class.getName()` là `edu.hidden.HiddenNamesDemo$Payload`. Đây là binary name hợp lệ của member class. Tên canonical thay `$` thành dấu chấm ở vị trí lớp thành viên, còn descriptor sử dụng `L...;` với `/` phân tách package.

**Tên hidden:** `first.isHidden()` là `true`. `first.getName()` bắt đầu bằng binary name của mẫu bytes cộng dấu `/` và hậu tố VM tạo. Chỉ kiểm tra prefix cho phép chương trình chạy ổn định dù phần suffix khác giữa các lần chạy.

**Descriptor:** `first.descriptorString()` bắt đầu bằng `Ledu/hidden/HiddenNamesDemo$Payload.` và kết thúc bằng `;`. Nhưng phần `.suffix` khiến chuỗi **không phải** descriptor kiểu hợp lệ để dùng với `ClassDesc.ofDescriptor()`. Vì thế `nominalMissing=true` và `nominalDescriptor=rejected`.

**Hai hidden classes:** Hai lần gọi `defineHiddenClass(bytes, false)` tạo **hai class khác nhau** dù đầu vào là cùng byte array, cùng lookup context, cùng class loader và cùng package. Do JVM cấp suffix phân biệt, hai `getName()` khác nhau. Không suy ra “cùng binary-name gốc” nghĩa là cùng một runtime class.

**Tra cứu bằng tên:** `Class.forName(first.getName())` ném `ClassNotFoundException`. Kết quả này là đặc tính thiết kế của hidden class, không có nghĩa class chưa được nạp hoặc không có đối tượng `Class<?>`.

**Array của hidden class:** `first.arrayType()` tạo `Class<?>` của kiểu mảng với component type là hidden class. **Array class tự nó không hidden** (`isHidden() == false`), nhưng không có nominal descriptor hợp lệ vì element type không có descriptor danh nghĩa. Điều này nhắc rằng không thể phát hiện “mảng chứa hidden class” chỉ bằng `array.isHidden()`; cần kiểm tra `array.getComponentType().isHidden()` nếu nghiệp vụ quan tâm.

### 4.3. Vì sao không in suffix và so sánh nguyên văn?

JVM chọn suffix cho từng hidden class; tên minh họa `/0x...` **không phải một chuỗi cố định trong hợp đồng Java**. Mã kiểm thử nên xác minh:

- `Class.isHidden()` là `true`.
- `getName()` có dạng `N_binary + "/" + suffix`.
- `descriptorString()` có dạng `L + N_internal + "." + suffix + ";"`.
- `getCanonicalName() == null`.
- `describeConstable().isEmpty()`.
- `Class.forName(hidden.getName())` không tìm được hidden class.

Đừng viết kiểm thử phụ thuộc toàn bộ runtime name chứa một số hex cụ thể; đừng lưu nó làm khóa để khôi phục đối tượng hidden class ở lần chạy sau.

## 5. Ví dụ đối chiếu: descriptor hợp lệ của lớp thông thường

Để phân biệt dễ hơn, chạy một chương trình chỉ sử dụng các lớp **không hidden**.

**Tệp `OrdinaryDescriptorDemo.java` (Java 17+):**

~~~java
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodType;

public class OrdinaryDescriptorDemo {
    public static void main(String[] args) throws Exception {
        System.out.println(String.class.getName());
        System.out.println(String.class.descriptorString());
        System.out.println(String[].class.getName());
        System.out.println(String[].class.descriptorString());
        System.out.println(int.class.descriptorString());
        System.out.println(
            MethodType.methodType(
                void.class, String.class, int.class
            ).descriptorString()
        );
        System.out.println(
            ClassDesc.ofDescriptor(
                String.class.descriptorString()
            ).descriptorString()
        );
        System.out.println(
            Class.forName(String.class.getName())
                == String.class
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OrdinaryDescriptorDemo.java
java OrdinaryDescriptorDemo
~~~

Kết quả:

~~~text
java.lang.String
Ljava/lang/String;
[Ljava.lang.String;
[Ljava/lang/String;
I
(Ljava/lang/String;I)V
Ljava/lang/String;
true
~~~

Giải thích:
- `getName()` của `String.class` trả về binary name `java.lang.String`.
- `descriptorString()` trả về descriptor `Ljava/lang/String;` hợp lệ.
- Mảng có `getName()` dùng `[L...;` với **dấu chấm package**, còn `descriptorString()` có **dấu gạch chéo package**.
- `MethodType.descriptorString()` trả về method descriptor `(Ljava/lang/String;I)V` (tham số String, int; kết quả void).
- `ClassDesc.ofDescriptor("Ljava/lang/String;")` tạo được danh nghĩa kiểu `String`.
- `Class.forName("java.lang.String")` tra cứu được lớp thông thường.

Cách so sánh này giúp thấy rõ: hidden class là **ngoại lệ có chủ đích** đối với giả định “mọi `getName()` đều là binary name, mọi `descriptorString()` đều là descriptor hợp lệ”.

## 6. Liên hệ với class loader, module và lookup

Một hidden class được định nghĩa từ `Lookup` trong cùng runtime package với lookup class. Trong ví dụ, package của lookup class và hidden class đều là `edu.hidden`. Đây là lý do `first.getPackageName()` vẫn có ý nghĩa bình thường dù `first.getName()` chứa suffix.

**Phân biệt ba khái niệm:**

1. **Defining class loader:** JVM ghi nhận class loader định nghĩa hidden class. Nhưng hidden class không được đưa vào cơ chế tra cứu theo binary name thông thường của loader như một lớp có tên danh nghĩa.
2. **`Lookup` trả về:** `defineHiddenClass()` trả về `MethodHandles.Lookup` trên chính hidden class đã tạo. Đây là một capability để thao tác qua các API method handles và giữ liên hệ tới `Class<?>` tương ứng.
3. **Runtime identity:** Hai hidden classes có thể dùng cùng loader và cùng mẫu bytes nhưng vẫn là **hai runtime classes khác nhau**. Suffix chỉ có tác dụng mô tả tên runtime; sự đồng nhất về lớp được xác định bằng `Class<?>` và identity, không bằng một “tên source” tự chế.

Một số tùy chọn tạo hidden class (ví dụ `NESTMATE` và `STRONG`) liên quan đến quan hệ nest/access hoặc vòng đời. Chúng **không biến hidden class thành lớp có binary name** để `Class.forName()` tìm được. Trước khi dùng các tùy chọn ấy trong framework, đọc hợp đồng API tương ứng; bài này tập trung vào cách gọi tên và descriptor.

### 6.1. Hidden class có thể dùng làm kiểu của biến hoặc phương thức không?

Trong **mã Java được biên dịch sẵn**, lớp khác không thể đặt binary name của hidden class vào constant pool để tham chiếu nó theo tên như một loại thông thường. Tuy nhiên lúc runtime, code đang giữ `Class<?>` hoặc `MethodHandle` có thể tương tác với hidden class và các thành viên của nó qua cơ chế hỗ trợ.

Tương tự, `MethodType` có thể chứa `Class<?>` của hidden class trong danh sách kiểu tham số/giá trị trả về lúc runtime. Nhưng `MethodType.descriptorString()` khi đó có thể là **chuỗi không hợp lệ theo JVMS** vì chứa phần hidden-class descriptor. Đừng tự biến chuỗi đó thành một định danh kiểu để lưu vào bytecode của một lớp khác.

### 6.2. Phân biệt “không tra cứu bằng tên” và “không thể sử dụng”

Không tra cứu được qua `Class.forName()` **không phải** một cơ chế bảo mật che giấu tuyệt đối. Code nào được cấp `Class<?>`, `Lookup` hoặc `MethodHandle` phù hợp vẫn có thể thao tác với class đó theo phạm vi quyền. Không dùng tính chất hidden như một boundary phân quyền hoặc sandbox độc lập.

## 7. Cách thiết kế API và logging bền vững

### 7.1. Khi nhận một `Class<?>` bất kỳ

Không phải mọi class đều là lớp thông thường. Nếu code làm nhiệm vụ diagnostic, hãy kiểm tra loại trước khi xử lý tên:

~~~java
// Đoạn minh họa bên trong một phương thức Java.
static String describeType(Class<?> type) {
    if (type.isHidden()) {
        return "hidden: " + type.getName();
    }
    return "ordinary/array/primitive: " + type.getTypeName();
}
~~~

Đoạn trên chỉ là **một method minh họa**, không phải tệp Java độc lập. Nếu cần phân biệt cả mảng có element type là hidden class, phải kiểm tra lặp `getComponentType()` hoặc dùng `componentType()` theo yêu cầu. Chỉ xét `type.isHidden()` không đủ đối với array class.

**Không làm thế này:** `Class.forName(clazz.getName())` như một cách “clone” hoặc “khôi phục” bất kỳ `Class<?>`. Nó không làm việc với hidden class (và với array/primitive còn có quy tắc riêng). Hãy truyền trực tiếp `Class<?>` hoặc capability thích hợp khi cùng runtime.

### 7.2. Chẩn đoán mà không phụ thuộc suffix

Đối với logs hoặc debug:
- Ghi `isHidden()`, package, module (nếu cần) và `getName()` như thông tin **diagnostic**.
- Tránh dùng toàn bộ `getName()` làm mã nhận diện ổn định giữa những lần chạy hoặc phiên bản VM.
- Khi thực sự cần liên hệ nhiều sự kiện trong cùng phiên làm việc, gán ID ứng dụng riêng cho đối tượng `Class<?>`/cấu trúc runtime mà bạn quản lý.
- Trong mã xử lý type signature, dùng `ClassDesc`/`MethodTypeDesc` cho **nominal types**. Nếu gặp hidden class, xử lý riêng bằng `Class<?>`/`MethodType`; không ép nó thành descriptor hợp lệ.
- Khi hiển thị tên lớp cho người dùng, không mặc định chuyển `getName()` thành “canonical class name”. `getCanonicalName()` có thể là `null`; `getName()` có thể chứa suffix hoặc dạng mảng đặc biệt.

### 7.3. API nào nên dùng cho từng mục tiêu?

| Nhu cầu | API / cách làm | Ghi chú |
| --- | --- | --- |
| Kiểm tra class có hidden không | `clazz.isHidden()` | Cách trực tiếp, không cần parse tên |
| In tên cho log | `clazz.getName()` | Có thể chứa suffix không ổn định |
| Lấy canonical name | `clazz.getCanonicalName()` | `null` với hidden class |
| Lấy mô tả kiểu | `clazz.descriptorString()` | Hidden class: chuỗi **không phải** descriptor JVMS hợp lệ |
| Lấy nominal descriptor | `clazz.describeConstable()` | `Optional.empty()` khi hidden |
| Tạo `ClassDesc` từ descriptor hợp lệ | `ClassDesc.ofDescriptor(descriptor)` | Không dùng descriptor của hidden class |
| Tải lớp theo binary name | `Class.forName(name)` / loader APIs | Không tìm được hidden class bằng runtime name |
| Thao tác với class đã tạo | Giữ `Class<?>` hoặc `Lookup` | Có thể dùng reflection/method handles phù hợp |
| Lấy kiểu phần tử của array | `arrayClass.getComponentType()` | Array không hidden dù phần tử có thể hidden |
| Hiểu package runtime | `clazz.getPackageName()` | Suffix không tạo package mới |
| Kiểm tra hai runtime classes giống nhau | `classA == classB` | Không dùng source name hoặc binary-name gốc |

## 8. Những lỗi phổ biến

**Lỗi 1 — “Mọi kết quả `Class.getName()` đều là binary name.”**  
Sai. Với hidden class, nó có dạng `N + "/" + suffix` và không phải binary name. Với array, `getName()` còn có cú pháp riêng.

**Lỗi 2 — “Lớp có tên runtime thì `Class.forName(name)` phải tìm được.”**  
Sai. Hidden class cố ý không discoverable qua lookup theo tên thông thường. Giữ `Class<?>` trực tiếp.

**Lỗi 3 — “`descriptorString()` luôn là descriptor JVM hợp lệ.”**  
Sai với hidden class hoặc kiểu mảng chứa hidden class. Nó có suffix với dấu chấm và không phải descriptor danh nghĩa.

**Lỗi 4 — “`ClassDesc.ofDescriptor(hidden.descriptorString())` phải thành công.”**  
Sai. `ClassDesc` mô tả kiểu danh nghĩa, còn hidden class không có danh tính danh nghĩa hợp lệ.

**Lỗi 5 — “`getCanonicalName() == null` đủ để xác định hidden class.”**  
Sai. Anonymous/local classes cũng có thể không có canonical name. Dùng `isHidden()`.

**Lỗi 6 — “`$` trong tên nghĩa là hidden class.”**  
Sai. Member class thông thường có binary name chứa `$`. Hidden class được nhận diện bằng `isHidden()`.

**Lỗi 7 — “Suffix `0x...` là mã ID có thể lưu lâu dài.”**  
Sai. Đó là chi tiết runtime; không hardcode, không suy ra hợp đồng ổn định hoặc khôi phục class trong lần chạy khác.

**Lỗi 8 — “Hai lần define cùng bytes chỉ tạo một class.”**  
Sai. Hai lần `defineHiddenClass()` tạo hai runtime classes khác nhau. Đối tượng `Class<?>` cũng khác nhau.

**Lỗi 9 — “Nếu mảng có phần tử hidden thì bản thân array.isHidden() phải true.”**  
Sai. Array class không phải hidden class, nhưng component type có thể hidden và không có nominal descriptor.

**Lỗi 10 — “Hidden có nghĩa không ai truy cập được.”**  
Sai. Code đã giữ `Class<?>`/`Lookup` có thể tương tác theo quyền. Hidden chủ yếu loại bỏ khả năng đặt tên/tìm theo tên danh nghĩa.

## 9. Tự kiểm tra

**Câu 1.** Một hidden class được tạo từ class file có internal name `demo/Task`. `getName()` và `descriptorString()` có những dạng nào?

**Đáp án:** `getName()` có dạng `demo.Task/suffix`; `descriptorString()` có dạng `Ldemo/Task.suffix;`. `suffix` do VM sinh. Cả hai **không phải** các danh tính danh nghĩa có thể dùng như binary name hoặc field descriptor hợp lệ.

**Câu 2.** Vì sao `hidden.describeConstable()` là empty dù `hidden.getName()` không rỗng?

**Đáp án:** `getName()` trả chuỗi mô tả tên runtime; `describeConstable()` cần một **nominal descriptor**. Hidden class cố ý không có nominal descriptor.

**Câu 3.** Một member class `demo.Outer.Inner` thường có binary name gì? Có phải hidden không?

**Đáp án:** Thường là `demo.Outer$Inner`. Không suy ra hidden từ dấu `$`; kiểm tra `isHidden()`.

**Câu 4.** Dùng `Class.forName(hidden.getName())` có lấy lại hidden class không?

**Đáp án:** Không. Hidden class không được discover qua cơ chế tìm theo binary name. Cần giữ `Class<?>` hoặc capability runtime đã có.

**Câu 5.** `hidden.arrayType().isHidden()` trả về gì? Vì sao vẫn phải quan tâm component type?

**Đáp án:** `false` vì array class không hidden; `array.getComponentType().isHidden()` là `true` nếu component là hidden. Mảng đó cũng không có nominal descriptor hợp lệ do element type là hidden.

**Câu 6.** Có nên dùng đầy đủ tên `pkg.Name/0x...` làm ID persistent cho một class generated không?

**Đáp án:** Không. Suffix phụ thuộc class được sinh trong runtime; dùng ID do ứng dụng quản lý nếu cần ổn định và giữ trực tiếp đối tượng `Class<?>` trong cùng tiến trình.

## 10. Tóm tắt điểm cốt lõi

- **Lớp thường:** `getName()` có thể là **binary name**, `descriptorString()` trả **descriptor hợp lệ**.
- **Hidden class:** `getName() = N_binary + "/" + suffix` là **runtime name không hợp lệ như binary name**.
- **Hidden descriptor:** `"L" + N_internal + "." + suffix + ";"` là chuỗi mô tả nhưng **không phải descriptor hợp lệ theo JVMS**.
- **Không có nominal identity:** `getCanonicalName() == null`, `describeConstable().isEmpty()`, và tra cứu bằng `Class.forName`/`ClassLoader.loadClass` theo runtime name không thành công.
- **Sử dụng đúng:** Giữ `Class<?>` / `Lookup` / `MethodHandle`, kiểm tra `isHidden()`, tránh hardcode suffix do JVM sinh.
- **Đối với mảng:** `array.isHidden()` là `false` ngay cả khi phần tử là hidden class; cần kiểm tra component type và hiểu rằng nominal descriptor không tồn tại.

## Tài liệu chính thức (vẫn áp dụng)

- [Oracle JDK 26 — `Class`: Hidden Classes, `getName`, `descriptorString`, `describeConstable`, `isHidden`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html)
- [Oracle JDK 24 — `MethodHandles.Lookup#defineHiddenClass`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Oracle Java 15 Release Notes — JEP 371 Hidden Classes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html)
- [Java Virtual Machine Specification — `4.2 Binary Names, `4.3 Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
- [Java SE 26 — `ClassDesc` (nominal type descriptor)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/constant/ClassDesc.html)
