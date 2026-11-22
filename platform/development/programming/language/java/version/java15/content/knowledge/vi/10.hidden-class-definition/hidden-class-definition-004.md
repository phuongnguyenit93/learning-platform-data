# Ràng buộc cùng package với lookup class khi định nghĩa hidden class (Java 15)

> **Mục tiêu:** Hiểu và sử dụng đúng quy tắc **class file bytes phải khai báo package trùng với package của `MethodHandles.Lookup.lookupClass()`** khi gọi `Lookup.defineHiddenClass(...)`; biết khác biệt giữa package name và runtime package, yêu cầu về quyền của `Lookup`, các lỗi thường gặp và cách tạo lookup cho package đích. Bài dùng các API **chính thức từ Java 15, vẫn được hỗ trợ trên Java hiện đại**, với chương trình **Java 17+** biên dịch/chạy được. Tránh kỹ thuật legacy, API nội bộ và những giả định chưa được JVM bảo đảm.

## 1. Hidden class được tạo trong ngữ cảnh của một Lookup

**Hidden class** là class/interface được JVM định nghĩa động từ bytecode và không có tên nhị phân thông thường để chương trình khác tìm lại bằng `Class.forName` hay `ClassLoader.loadClass`. JEP 371 chuẩn hóa khả năng này ở **JDK 15**; các framework cần sinh implementation tại runtime có thể dùng nó.

API chính:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, true);

Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Trong đó:

- `classBytes` là `byte[]` chứa một **class file JVM hợp lệ**. Tệp có thể đến từ compiler hoặc bộ sinh bytecode đúng chuẩn.
- `lookup` là capability mô tả **class, package, module, class loader và quyền truy cập** của bên định nghĩa.
- `initialize` điều khiển việc **khởi tạo class** trong lúc định nghĩa; **không tự tạo instance** hoặc gọi constructor.
- `hiddenLookup` là lookup **mới**, có ngữ cảnh class vừa được định nghĩa; `lookupClass()` trả về `Class<?>` của hidden class.
- Hidden class có runtime name đặc biệt, **không thể tra cứu lại bằng tên** như một class thông thường; phải giữ `Class`, `Lookup` hoặc method handles để sử dụng.

**Điểm khác biệt quan trọng:** API không chấp nhận một class file bất kỳ và cũng không đơn thuần nạp file vào một class loader tùy ý. Nó định nghĩa class **trong package của lookup class** với các quy tắc kiểm tra nghiêm ngặt.

## 2. Hợp đồng “cùng package” thực sự có nghĩa gì?

Javadoc của `Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` yêu cầu **class name được khai báo trong bytes phải cùng package với `lookup.lookupClass()`**.

Giả sử:

~~~java
package demo.host;

public class Host {
    // MethodHandles.lookup() gọi bên trong đây.
}
~~~

Thì `MethodHandles.lookup()` gọi trong `Host` tạo lookup với:

~~~java
lookup.lookupClass() == Host.class; // true
lookup.lookupClass().getPackageName(); // "demo.host"
~~~

Một class file từ:

~~~java
package demo.host;

public class SamePayload {
}
~~~

là **đúng package**. Nhưng class file từ:

~~~java
package demo.other;

public class OtherPayload {
}
~~~

là **khác package**. Khi dùng lookup của `Host` gọi `defineHiddenClass(bytesOfOtherPayload, false)`, JVM ném **`IllegalArgumentException`**.

Quy tắc được xét theo **tên class có trong cấu trúc class file** (internal name, ví dụ `demo/other/OtherPayload`). Di chuyển file `OtherPayload.class` sang thư mục `demo/host` hay đổi tên file trên đĩa **không làm đổi** internal name. Việc `OtherPayload` có modifier `public` cũng không bỏ được ràng buộc package.

**Không cần class bytes có tên trùng lookup class.** `Host` và `SamePayload` có tên class khác nhau; chỉ **tên package** phải khớp. Sau khi định nghĩa thành công, JVM biến danh tính class thành một hidden class riêng; việc tên gốc của bytecode không trở thành tên nhị phân tra cứu thông thường là đặc tính có chủ đích.

## 3. Runtime package còn liên quan đến class loader và module

**Tên package trong source** và **runtime package** không phải hai khái niệm hoàn toàn giống nhau:

- Tên package Java là phần như `demo.host` được khai báo trong source và encoded trong class file.
- Ở JVM, quyền truy cập package gắn với ngữ cảnh **defining class loader** và module/runtime package, không chỉ một chuỗi tên.
- Class hidden được định nghĩa với **defining class loader, runtime package và protection domain** theo ngữ cảnh lookup class.
- Hai class cùng viết `package demo.host;` nhưng do **hai class loaders độc lập** định nghĩa không mặc nhiên trở thành thành viên cùng runtime package có thể truy cập package-private lẫn nhau.

Vì vậy, khi debug, cần hỏi **lookup class thực tế là ai, được nạp bởi loader nào, và bytes khai báo package gì**, thay vì chỉ nhìn path của file.

Ví dụ kiểm tra sau khi định nghĩa thành công:

~~~java
Class<?> defined = hiddenLookup.lookupClass();

System.out.println(defined.isHidden());          // true
System.out.println(defined.getPackageName());     // "demo.host"
System.out.println(
        defined.getClassLoader() == Host.class.getClassLoader()); // true
~~~

Đoạn này được đặt trong method thuộc class `Host`, với biến `hiddenLookup` đã định nghĩa hợp lệ. Nó chỉ minh họa các quan sát có ý nghĩa; chương trình hoàn chỉnh ở mục 5.

## 4. Hai điều kiện phải đúng đồng thời

| Điều kiện | Cách kiểm tra | Lỗi khi không đáp ứng |
| --- | --- | --- |
| Class file chứa class thuộc **cùng package** với `lookup.lookupClass()` | Kiểm tra package từ internal name của class file và lookup class | `IllegalArgumentException` |
| Lookup có **full privilege access** | `lookup.hasFullPrivilegeAccess()` | `IllegalAccessException` |
| Bytes có cấu trúc class file hợp lệ, được runtime JDK hỗ trợ | Dùng compiler/bộ sinh bytecode hợp lệ; kiểm tra JDK target | `ClassFormatError`, `UnsupportedClassVersionError`, `VerifyError` hoặc các `LinkageError` khác tùy nguyên nhân |
| Tham số không `null` và class file không có kiểu cấu trúc bị cấm | Đúng hợp đồng API | `NullPointerException` hoặc `IllegalArgumentException` tùy lỗi |

`MethodHandles.lookup()` được gọi trong code có quyền phù hợp thường tạo lookup với full privilege access trong module của caller. Nhưng **`MethodHandles.publicLookup()`** chỉ là lookup công khai hạn chế; nó **không thể** dùng để định nghĩa hidden class.

~~~java
MethodHandles.Lookup owner = MethodHandles.lookup();
System.out.println(owner.hasFullPrivilegeAccess()); // true

MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
System.out.println(publicOnly.hasFullPrivilegeAccess()); // false
~~~

**Đúng package chưa đủ**, vì một lookup ở đúng package nhưng thiếu full privilege vẫn thất bại. **Đủ quyền chưa đủ**, vì bytes khác package vẫn bị từ chối.

Đừng nhầm `Lookup.defineHiddenClass(...)` với `Lookup.defineClass(byte[])`: API thứ hai tạo **class có tên bình thường** và yêu cầu `PACKAGE` access, còn **hidden class đòi full privilege access**. Cả hai vẫn ràng buộc package khai báo trong bytes.

## 5. Chương trình Java 17+ có thể chạy độc lập để kiểm chứng

Để tránh phụ thuộc thư viện sinh bytecode ngoài JDK, ta biên dịch bốn class thật bằng `javac` rồi đọc bytes từ `.class`. Thí nghiệm chạy trên **classpath trong cùng unnamed module**, để có thể phân biệt lỗi package và lỗi quyền bằng những đường đi rõ ràng.

Cây tệp:

~~~text
demo/
  host/
    Host.java
    SamePayload.java
  other/
    OtherAnchor.java
    OtherPayload.java
~~~

### 5.1. `demo/host/SamePayload.java`

~~~java
package demo.host;

public class SamePayload {
    public String greet() {
        return "same-ok";
    }
}
~~~

### 5.2. `demo/other/OtherPayload.java`

~~~java
package demo.other;

public class OtherPayload {
    public String greet() {
        return "other-ok";
    }
}
~~~

### 5.3. `demo/other/OtherAnchor.java`

~~~java
package demo.other;

public class OtherAnchor {
}
~~~

`OtherAnchor` là class bình thường, giúp tạo lookup **đúng package `demo.other`** khi được quyền. Nó không chứa hành vi nghiệp vụ.

### 5.4. `demo/host/Host.java`

~~~java
package demo.host;

import demo.other.OtherAnchor;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class Host {
    static String call(MethodHandles.Lookup hidden) throws Throwable {
        Class<?> type = hidden.lookupClass();
        Object instance = hidden.findConstructor(type,
                MethodType.methodType(void.class)).invoke();
        return (String) hidden.findVirtual(type, "greet",
                MethodType.methodType(String.class)).invoke(instance);
    }

    public static void main(String[] args) throws Throwable {
        byte[] same = Files.readAllBytes(
                Path.of("out/demo/host/SamePayload.class"));
        byte[] other = Files.readAllBytes(
                Path.of("out/demo/other/OtherPayload.class"));
        MethodHandles.Lookup original = MethodHandles.lookup();
        MethodHandles.Lookup hidden = original.defineHiddenClass(same, true);

        System.out.println("lookupPackage="
                + original.lookupClass().getPackageName());
        System.out.println("hiddenPackage="
                + hidden.lookupClass().getPackageName());
        System.out.println("isHidden=" + hidden.lookupClass().isHidden());
        System.out.println("sameLoader=" + (hidden.lookupClass().getClassLoader()
                == Host.class.getClassLoader()));
        System.out.println("samePackageCall=" + call(hidden));

        try {
            original.defineHiddenClass(other, false);
            System.out.println("differentPackage=UNEXPECTED");
        } catch (IllegalArgumentException expected) {
            System.out.println("differentPackage=IllegalArgumentException");
        }

        try {
            MethodHandles.publicLookup().defineHiddenClass(same, false);
            System.out.println("publicLookup=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("publicLookup=IllegalAccessException");
        }

        MethodHandles.Lookup restricted = original.in(OtherAnchor.class);
        System.out.println("restrictedFull=" + restricted.hasFullPrivilegeAccess());
        try {
            restricted.defineHiddenClass(other, false);
            System.out.println("restrictedLookup=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("restrictedLookup=IllegalAccessException");
        }

        MethodHandles.Lookup otherLookup = MethodHandles.privateLookupIn(
                OtherAnchor.class, original);
        System.out.println("targetPackage="
                + otherLookup.lookupClass().getPackageName());
        System.out.println("targetFull=" + otherLookup.hasFullPrivilegeAccess());
        MethodHandles.Lookup otherHidden =
                otherLookup.defineHiddenClass(other, true);
        System.out.println("otherPackageCall=" + call(otherHidden));

        try {
            Class.forName(hidden.lookupClass().getName());
            System.out.println("byName=UNEXPECTED");
        } catch (ClassNotFoundException expected) {
            System.out.println("byName=ClassNotFoundException");
        }
    }
}
~~~

### 5.5. Biên dịch và chạy

Đứng tại **thư mục chứa `demo`**, chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out demo/host/Host.java demo/host/SamePayload.java demo/other/OtherAnchor.java demo/other/OtherPayload.java
java -cp out demo.host.Host
~~~

Lệnh `javac` tạo bytes class ở `out/demo/host` và `out/demo/other`; đường dẫn tương đối trong `Host` phụ thuộc việc chạy `java` từ đúng thư mục gốc của ví dụ. Đây là **bốn source files**, không phải một `Host.java` duy nhất chứa toàn bộ class.

**Stdout chính xác đã kiểm chứng:**

~~~text
lookupPackage=demo.host
hiddenPackage=demo.host
isHidden=true
sameLoader=true
samePackageCall=same-ok
differentPackage=IllegalArgumentException
publicLookup=IllegalAccessException
restrictedFull=false
restrictedLookup=IllegalAccessException
targetPackage=demo.other
targetFull=true
otherPackageCall=other-ok
byName=ClassNotFoundException
~~~

Các dòng output có thể được so sánh nguyên văn. Không cần `--enable-preview`, `--add-opens` hay sử dụng `jdk.internal` để chạy ví dụ này.

## 6. Giải thích thí nghiệm cùng package

Trong `Host`:

~~~java
MethodHandles.Lookup original = MethodHandles.lookup();
MethodHandles.Lookup hidden =
        original.defineHiddenClass(same, true);
~~~

- `original.lookupClass()` chính là `demo.host.Host`; package của nó là `demo.host`.
- `SamePayload.class` cũng khai báo `demo.host` trong class file.
- `original` được tạo trong `Host` và có full privilege access.
- Do cả hai điều kiện đúng, JVM tạo hidden class; `hidden.lookupClass().isHidden() == true`.
- Hidden class được định nghĩa với class loader tương ứng lookup class; ví dụ in `sameLoader=true`.
- `Host.call(hidden)` dùng **method handle cho constructor** và `greet()` để chứng minh class mới có thể được khởi tạo và gọi; kết quả là `same-ok`.

Đừng suy từ `initialize=true` rằng một object đã được tạo. Nó điều khiển **class initialization**, còn constructor phải được gọi riêng.

`hidden.lookupClass().getName()` biểu diễn tên runtime đặc biệt có suffix của hidden class. Nó **không** phải binary name tra cứu được; vì vậy `Class.forName(hidden.lookupClass().getName())` thất bại bằng `ClassNotFoundException`. Nếu framework cần dùng class sau khi tạo, giữ `Class<?>`/`Lookup`/`MethodHandle` thay vì lưu tên rồi đi tìm lại.

## 7. Giải thích thí nghiệm package sai và lookup thiếu quyền

### Package khác: `IllegalArgumentException`

~~~java
original.defineHiddenClass(other, false);
~~~

Bytes `other` được biên dịch từ `demo.other.OtherPayload`, còn `original` trỏ về `demo.host.Host`. Do không cùng package, JVM từ chối bằng **`IllegalArgumentException`**.

Những thao tác sau **không sửa** được điều kiện package:

- Chuyển hoặc đổi tên file `OtherPayload.class` trên disk.
- Đặt `initialize=false` thay vì `true`.
- Thêm `ClassOption.NESTMATE` hay `ClassOption.STRONG`.
- Dùng `publicLookup()` hoặc chỉ làm `OtherPayload` thành class `public`.
- Bắt ngoại lệ rồi cố tìm class bằng `Class.forName`.

Để sửa đúng, **tạo class bytes có package trùng lookup** hoặc **có một lookup hợp lệ thuộc package mà bytes đã khai báo**.

### Lookup thiếu quyền: `IllegalAccessException`

~~~java
MethodHandles.publicLookup().defineHiddenClass(same, false);
~~~

`publicLookup()` không có full privilege access. Thí nghiệm trả **`IllegalAccessException`**. Điều này độc lập với chuyện bytes có thể thuộc package nào; nên xác định quyền lookup trước khi chọn cách tạo class.

### `Lookup.in(...)` không tự leo thang quyền

~~~java
MethodHandles.Lookup restricted = original.in(OtherAnchor.class);
System.out.println(restricted.hasFullPrivilegeAccess()); // false
~~~

`in` đổi lookup class làm ngữ cảnh tra cứu nhưng có thể **làm giảm quyền**. Trong thí nghiệm, `restricted` có lookup class thuộc `demo.other` nhưng không đủ full privilege; `restricted.defineHiddenClass(other, false)` ném **`IllegalAccessException`**. Không có lối tắt “đúng package rồi cấp tự động mọi quyền”.

## 8. Tạo lookup đúng package bằng `privateLookupIn` khi điều kiện cho phép

Trong thí nghiệm, `Host` và `OtherAnchor` thuộc **cùng unnamed module** (chạy trên cùng classpath). Đoạn sau hợp lệ:

~~~java
MethodHandles.Lookup original = MethodHandles.lookup();
MethodHandles.Lookup otherLookup =
        MethodHandles.privateLookupIn(
                OtherAnchor.class, original);

MethodHandles.Lookup otherHidden =
        otherLookup.defineHiddenClass(other, true);
~~~

Lúc đó `otherLookup.lookupClass()` là `OtherAnchor.class` thuộc `demo.other`; `other` chứa class bytes của `OtherPayload` cũng thuộc `demo.other`. Vì thuộc cùng module và caller đủ quyền, `otherLookup.hasFullPrivilegeAccess() == true` trong thí nghiệm, nên `defineHiddenClass` thành công và `greet()` trả `other-ok`.

**Không mở rộng kết luận sai sang nhiều module:** `privateLookupIn` có các điều kiện bảo vệ module. Khi caller và target thuộc **hai named modules khác nhau**, caller module phải **đọc** target module và package đích phải **opens** cho caller module để có deep reflection. Ngay cả khi được trả một private lookup xuyên module, lookup này **bị loại `MODULE` access**, nên **không có full privilege access cần thiết** cho `defineHiddenClass`.

Do đó, “đã mở package cho reflection” **không đồng nghĩa** có quyền định nghĩa hidden class trong module đó. Cách rõ ràng là để code tin cậy **trong module/package đích** sở hữu hoặc thực thi việc định nghĩa, thay vì giả định một lookup xuyên module có thể tạo class tùy ý.

### Vì sao không chuyển lookup bằng `Lookup.in`?

`Lookup.in(Target.class)` **không** tương đương `privateLookupIn(Target.class, caller)`. Phương thức `in` thay đổi lookup context trong giới hạn quyền đang có; nó không tự xác thực khả năng deep reflection mới của caller hoặc cấp lại quyền `PRIVATE`/`MODULE` đã mất. Luôn kiểm tra khả năng thực tế và xử lý `IllegalAccessException`.

## 9. Cùng package không có nghĩa cùng nest

Cùng package theo Java có ý nghĩa đối với **package-private members**. Nhưng nó **không tự cấp quyền truy cập các `private` members của một class khác**.

Khi cần hidden class tham gia nest của lookup class, API hỗ trợ option hiện hành:

~~~java
MethodHandles.Lookup hidden = lookup.defineHiddenClass(
        bytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

`NESTMATE` cho phép hidden class trở thành **nestmate** theo quy tắc JVM, để bytecode có thể tương tác private members trong cùng nest khi hợp lệ. Nhưng option này **không làm thay đổi package của class bytes**, và không bù quyền `Lookup` thiếu.

| Câu hỏi | Trả lời |
| --- | --- |
| Class có bytes khác package, thêm `NESTMATE` có thành công? | **Không**, vẫn vi phạm điều kiện package |
| Hidden class cùng package tự nhiên được vào nest của `Host`? | **Không**, chỉ khi dùng cơ chế nest membership phù hợp |
| Cùng package cho quyền gọi mọi private method? | **Không**, private vẫn chịu kiểm tra nest/access |
| Dùng `STRONG` có sửa lỗi quyền/package? | **Không**, nó điều khiển mối liên hệ mạnh với defining loader, liên quan vòng đời/unloading |

Chỉ dùng những option này khi thiết kế framework thực sự cần; với bài toán định nghĩa class cùng package đơn giản, không cần truyền option nào.

## 10. Phân biệt `defineHiddenClass` và `defineClass`

| Thuộc tính | `defineHiddenClass(byte[], boolean, ...)` | `defineClass(byte[])` |
| --- | --- | --- |
| Có từ Java | **15** | **9** |
| Kết quả | `MethodHandles.Lookup` cho hidden class | `Class<?>` của class bình thường |
| Tên class | Hidden name, không phải binary name tra cứu thường | Tên nhị phân bình thường |
| Quyền bắt buộc | **Full privilege access** | **PACKAGE access** |
| Package trong bytes | Phải trùng package lookup class | Phải trùng package lookup class |
| Dùng phù hợp | Framework/runtime tạo implementation riêng biệt | Khi cần class mang tên bình thường, có thể tra cứu/tham chiếu theo tên |
| Vòng đời | Cơ chế hidden class với lựa chọn unloading/strong liên quan loader | Cơ chế quản lý class có tên bình thường |

Cả hai đều có ràng buộc cùng package, nhưng **không được suy luận cùng yêu cầu quyền**. `defineHiddenClass` không phải công cụ thay thế class loader chung để tự ý đưa code vào package bất kỳ.

Hidden class **không phải sandbox**: bytecode có thể thực thi logic và ảnh hưởng tài nguyên theo quyền JVM của nó. Chỉ nạp class bytes có nguồn gốc đáng tin hoặc qua quy trình sinh bytecode được kiểm soát.

## 11. Những lỗi thường gặp và cách chẩn đoán

1. **Lấy lookup từ class bên ngoài package đích rồi cố định nghĩa class đích.** Kiểm tra `lookup.lookupClass().getPackageName()` và internal class name của bytes.
2. **Đổi tên file `.class` và tưởng package đã đổi.** Tên bên trong class file mới là nguồn dữ liệu chính; cần biên dịch/sinh lại bytes đúng package.
3. **Thấy class `public` rồi cho rằng đã đủ.** Quyền truy cập public class khác với quyền định nghĩa class mới trong package của nó.
4. **Dùng `publicLookup()` vì method cần gọi là public.** API định nghĩa hidden class yêu cầu full privilege access, không chỉ quyền gọi public methods.
5. **Dùng `Lookup.in` như một phép cấp thêm `PRIVATE`/`MODULE`.** `in` chỉ giữ hoặc giới hạn quyền, không leo thang quyền.
6. **Cho rằng `privateLookupIn` xuyên module luôn đủ quyền define.** Lookup xuyên module mất `MODULE` access; check `hasFullPrivilegeAccess()` và thiết kế lại ownership.
7. **Thêm `NESTMATE` để chữa lỗi package.** Option tác động quan hệ nest, không đổi package name.
8. **Dùng `initialize=true` rồi tưởng đã có instance.** Class initialization và object construction là hai giai đoạn khác nhau.
9. **Lưu tên hidden class để `Class.forName` về sau.** Hidden class không tra cứu theo binary name bình thường; giữ `Class/Lookup`.
10. **Bắt mọi `LinkageError` như lỗi package.** Bytecode có thể sai version, verifier, phụ thuộc, superclass/interface; phân loại theo ngoại lệ thật.
11. **Không kiểm soát nguồn bytecode.** Định nghĩa class từ bytes không đáng tin không phải cách cô lập hành vi nguy hiểm.
12. **Suy luận cùng runtime package chỉ vì trùng chuỗi `package`.** Cần xét defining class loader và module.

Khi debug, nên ghi **loại ngoại lệ**, **lookup class/package/module/loader** và tên lớp mà bộ sinh bytes dự định tạo; không cần dump toàn bộ bytecode hoặc thông tin nhạy cảm. Để xem package của class file compile bình thường, có thể dùng công cụ JDK:

~~~bash
javap -classpath out demo.host.SamePayload
javap -classpath out demo.other.OtherPayload
~~~

Đây là hai class nguồn bình thường; lệnh chỉ xem thông tin class file. Nó không có nghĩa hidden class được tra cứu bằng `javap` sau khi `defineHiddenClass`.

## 12. Thiết kế framework: chọn package sở hữu một cách có chủ đích

Một luồng đơn giản:

~~~text
Code đáng tin ở package/module chủ đích
      |
      | MethodHandles.lookup() với đủ quyền
      v
Lookup có full privilege access
      |
      | Class bytes khai báo cùng package
      v
defineHiddenClass(bytes, initialize, options)
      |
      v
Lookup của hidden class -> Class<?> -> method handles/instance
~~~

Những quyết định nên viết rõ trong thiết kế:

- **Package nào sở hữu class mới?** Nếu framework `framework.internal` cần tạo một class trong `app.domain`, không thể chỉ dùng lookup của `framework.internal` cùng bytes tự nhận `app.domain`.
- **Ai được giữ lookup có full privilege?** Đây là capability nhạy cảm; không chia sẻ trực tiếp cho plugin không đáng tin hoặc thư viện không kiểm soát.
- **Bytecode được sinh ra thế nào?** Dùng compiler hoặc bộ sinh class-file hợp lệ, nhất quán với package, superclass, interface và JDK target.
- **Có thật sự cần hidden class?** Với logic ứng dụng thông thường, class/record/interface/lambda hay proxy API mức cao có thể phù hợp hơn.
- **Thời điểm chạy static initializer?** `initialize=true` có thể làm code trong `<clinit>` chạy khi định nghĩa; chỉ dùng bytes hợp lệ và đáng tin.
- **Có cần `NESTMATE`?** Chỉ thêm khi bytecode cần private access trong nest phù hợp.
- **Cần vòng đời như thế nào?** `STRONG` điều khiển quan hệ với class loader, không sửa các lỗi package/quyền.

Thiết kế module rõ ownership giúp tránh việc gửi lookup quyền cao qua nhiều lớp tích hợp, giảm rủi ro và dễ viết test.

## 13. Bài luyện tập và tiêu chí đạt

**Bài 1 — Same package.** Biên dịch `Host` và `SamePayload` cùng `demo.host`. **Đạt** khi thấy `isHidden=true`, `hiddenPackage=demo.host`, `sameLoader=true` và `samePackageCall=same-ok`.

**Bài 2 — Mismatch.** Giữ lookup của `Host` nhưng dùng bytes `OtherPayload` thuộc `demo.other`. **Đạt** khi bắt `IllegalArgumentException` và giải thích rõ tên package được kiểm tra **trong class file**, không phải path/tên file.

**Bài 3 — Lookup quyền thấp.** Dùng `publicLookup()` và `original.in(OtherAnchor.class)`. **Đạt** khi giải thích các kết quả `IllegalAccessException` và `restrictedFull=false`, không nhầm với lỗi package.

**Bài 4 — Đổi ngữ cảnh đúng cách.** Trong cùng unnamed module, dùng `privateLookupIn(OtherAnchor.class, original)` rồi define bytes của `OtherPayload`. **Đạt** khi được `targetFull=true` và `otherPackageCall=other-ok`.

**Bài 5 — Module boundary.** Mô tả trường hợp caller và target ở hai named modules, dù target package đã `opens` cho caller. **Đạt** khi biết private lookup xuyên module **không tự đủ full privilege** để định nghĩa hidden class.

**Bài 6 — Lookup và nest.** Trả lời: `ClassOption.NESTMATE` có sửa mismatch package không? Hidden class cùng package tự được phép truy cập private methods của `Host` không? **Đạt** khi cả hai câu trả lời là **không**, kèm giải thích ranh giới package và nest.

**Bài 7 — Không tra theo tên.** Thử `Class.forName(hidden.lookupClass().getName())`. **Đạt** khi dự đoán `ClassNotFoundException` và biết giữ lookup/class object để sử dụng hidden class.

## 14. Nguồn chính thức

- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): tính năng hidden class chính thức từ JDK 15, mục đích và ràng buộc ngữ cảnh.
- [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): đặc tả `defineHiddenClass`, yêu cầu package, full privilege access, `Lookup.in`, `defineClass`, `NESTMATE` và `STRONG`.
- [Oracle Java SE 25 — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, `privateLookupIn`, điều kiện module.
- [Oracle Java SE 25 — Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): hidden name không phải binary name, `Class.isHidden()`.
- [JVM Specification 25 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): runtime package, class loader và quá trình định nghĩa/liên kết class.

**Ghi nhớ:** `Lookup.defineHiddenClass` yêu cầu **hai điều kiện độc lập**: class bytes phải khai báo **cùng package với lookup class**, và lookup phải có **full privilege access**. Lỗi package thường là `IllegalArgumentException`; lookup thiếu quyền là `IllegalAccessException`. `Lookup.in` không tự mở rộng quyền; `privateLookupIn` phụ thuộc module boundary; `NESTMATE` không thay thế điều kiện package. Dùng đúng class bytes và đúng lookup trong package chủ đích, rồi giữ kết quả `Lookup/Class` để sử dụng.
